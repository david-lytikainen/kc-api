import asyncio
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks, HTTPException, UploadFile
import jwt
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app import main, routes
from app.dto import CategoryCreateRequest, CategoryUpdateRequest, CommissionCommentRequest, GalleryInquiryRequest, GalleryReorderRequest, QuoteRequest, ReviewRequest, StatusUpdateRequest
from app.models import Base, CommissionCategory, GalleryOrder
from app.reads import read_all, read_one, refresh


class SqlReadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.reads = []
        event.listen(self.engine, 'before_cursor_execute', self.capture_read)
        for target, value in [(routes, self.sessions), (main, self.sessions)]:
            patcher = patch.object(target, 'SessionLocal', value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in [('send_plain_email', Mock(return_value=True)), ('AWS_REGION', 'test'), ('S3_BUCKET', 'test'), ('get_s3_client', Mock(return_value=Mock(generate_presigned_url=lambda *a, **k: 'https://example.com/image'))), ('STRIPE_SECRET_KEY', 'test'), ('create_review_reward', Mock())]:
            patcher = patch.object(routes, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.auth = 'Bearer ' + jwt.encode({'sub': 'admin'}, routes.JWT_SECRET, algorithm='HS256')
        main.sync_bootstrap_lookup_tables()
        main.sync_bootstrap_lookup_tables()

    def capture_read(self, connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith('select'):
            self.reads.append(statement)

    def tearDown(self):
        self.engine.dispose()
        self.assertTrue(self.reads)
        for statement in self.reads:
            self.assertEqual(statement, statement.lower(), statement)

    def upload(self, name):
        return UploadFile(BytesIO(b'image fixture'), filename=name, headers=Headers({'content-type': 'image/png'}))

    def gallery(self):
        return routes.create_gallery_item(title='Blue Sky', description='Mixed CASE', price_amount='25', files=[self.upload('First.png'), self.upload('Second.png')], authorization=self.auth)

    def test_categories_bind_values_and_preserve_case(self):
        category = routes.create_category(CategoryCreateRequest(name="Portraits' OR 1=1 --"), self.auth)
        other = routes.create_category(CategoryCreateRequest(name='Oil Paint'), self.auth)
        self.assertEqual(len(routes.list_public_categories()), 2)
        with self.assertRaises(HTTPException) as duplicate:
            routes.create_category(CategoryCreateRequest(name='oil paint'), self.auth)
        self.assertEqual(duplicate.exception.status_code, 400)
        renamed = routes.update_category(category.id, CategoryUpdateRequest(name='Portraits', is_archived=True), self.auth)
        self.assertEqual(renamed.name, 'Portraits')
        self.assertEqual([item.id for item in routes.list_public_categories()], [other.id])
        self.assertEqual(len(routes.list_admin_categories(self.auth)), 2)
        with self.sessions() as session:
            self.assertEqual(read_all(session, CommissionCategory, 'select * from commission_categories where id in :ids', {'ids': []}), [])
            self.assertEqual(len(read_all(session, CommissionCategory, 'select * from commission_categories where id in :ids', {'ids': [category.id, other.id]})), 2)
            self.assertIsNone(read_one(session, CommissionCategory, 'select * from commission_categories where name = :name', {'name': "' OR 1=1 --"}))

    def test_gallery_images_reorder_replace_and_archive(self):
        item = self.gallery()
        self.assertEqual(item.title, 'Blue Sky')
        image_ids = [image.id for image in item.images]
        updated = routes.update_gallery_item(item.id, 'Blue Sky', 'Mixed CASE', '25', None, image_ids[::-1], [], self.auth)
        self.assertEqual([image.id for image in updated.images], image_ids[::-1])
        self.assertIn('Second.png', updated.s3_key)
        updated = routes.update_gallery_item(item.id, 'New Title', 'Still Mixed', '', None, None, [self.upload('Replacement.png')], self.auth)
        self.assertEqual(len(updated.images), 1)
        self.assertIsNone(updated.price_cents)
        self.assertEqual(routes.get_gallery_item(item.id).title, 'New Title')
        self.assertEqual(len(routes.list_gallery_items()), 1)
        self.assertEqual(len(routes.list_admin_gallery_items(self.auth)), 1)
        routes.reorder_gallery_items(GalleryReorderRequest(ordered_ids=[item.id]), self.auth)
        routes.reorder_gallery_items(GalleryReorderRequest(ordered_ids=[]), self.auth)
        with self.sessions() as session:
            self.assertEqual(session.scalar(text('select count(*) from gallery_item_images')), 1)
        second = self.gallery()
        routes.update_gallery_item(item.id, 'New Title', 'Still Mixed', '', False, None, [], self.auth)
        self.assertEqual([row.id for row in routes.list_gallery_items()], [second.id])
        admin_items = routes.list_admin_gallery_items(self.auth)
        self.assertEqual([row.id for row in admin_items], [second.id, item.id])
        self.assertFalse(admin_items[-1].is_published)
        with self.assertRaises(HTTPException) as archived:
            routes.get_gallery_item(item.id)
        self.assertEqual(archived.exception.status_code, 404)
        restored = routes.update_gallery_item(item.id, 'New Title', 'Still Mixed', '', True, None, [], self.auth)
        self.assertTrue(restored.is_published)
        self.assertEqual(len(restored.images), 1)
        self.assertEqual(len(routes.list_gallery_items()), 2)

    def comments(self, number):
        customer = routes.create_comment(number, CommissionCommentRequest(body='Customer CASE'), BackgroundTasks(), None)
        admin = routes.create_comment(number, CommissionCommentRequest(body='Admin CASE'), BackgroundTasks(), self.auth)
        self.assertEqual(customer.author_role, 'customer')
        self.assertEqual(admin.author_role, 'admin')
        with self.assertRaises(HTTPException) as forbidden:
            routes.update_comment(number, customer.id, CommissionCommentRequest(body='No'), self.auth)
        self.assertEqual(forbidden.exception.status_code, 403)
        updated = routes.update_comment(number, customer.id, CommissionCommentRequest(body='Edited CASE'), None)
        self.assertEqual(updated.body, 'Edited CASE')
        kind = routes.get_order(number, None).order_kind
        routes.update_comment_email_status(kind, customer.id, None, 'Test error')
        self.assertEqual(routes.get_order(number, None).comments[-2].email_error, 'Test error')
        routes.delete_comment(number, admin.id, self.auth)
        self.assertEqual(routes.get_order(number, None).comments[-1].body, 'Edited CASE')

    def test_commission_status_comments_review_and_admin_list(self):
        category = routes.create_category(CategoryCreateRequest(name='Portrait'), self.auth)
        order = asyncio.run(routes.create_commission_request('Mixed Name', 'buyer@example.com', '1234567890', category.id, '', 'Keep My CASE', 'Oil', 'Large', [self.upload('Reference.png')]))
        number = order.order_number
        self.assertEqual(order.status, 'submitted')
        self.assertEqual(order.instructions, 'Keep My CASE')
        self.assertEqual(len(order.files), 1)
        self.comments(number)
        quoted = routes.set_order_quote(number, QuoteRequest(quote_amount='123.45'), self.auth)
        self.assertEqual((quoted.status, quoted.quote_amount_cents), ('quoted', 12345))
        self.assertEqual(routes.decline_order(number).status, 'declined')
        for status in ['accepted', 'in_progress', 'shipped', 'delivered']:
            self.assertEqual(routes.update_order_status(number, StatusUpdateRequest(status=status), self.auth).status, status)
        self.assertIsNotNone(routes.confirm_order_received(number).customer_confirmed_at)
        review = routes.submit_order_review(number, ReviewRequest(rating=5, body='Great CASE'))
        self.assertEqual(review.review.body, 'Great CASE')
        self.assertFalse(review.review_discount_eligible)
        summary = routes.list_admin_orders(1, 10, self.auth)
        self.assertEqual(summary.total, 1)
        self.assertEqual(summary.items[0].status, 'delivered')

    def test_gallery_inquiry_paid_order_and_reward_lookup(self):
        item = self.gallery()
        inquiry = routes.create_gallery_inquiry(item.id, GalleryInquiryRequest(customer_email='buyer@example.com', body='First Question'))
        self.comments(inquiry.order_number)
        with self.sessions() as session:
            order = GalleryOrder(order_number='123456', gallery_item_id=item.id, item_title=item.title, item_image_url='https://example.com/image', amount_cents=2500, customer_name='Customer', customer_email='', stripe_checkout_session_id='cs_test')
            session.add(order)
            session.commit()
            refresh(session, order)
            self.assertIsNone(order.status)
            routes.mark_gallery_order_paid(session, order, {'customer_details': {'name': 'Mixed Buyer', 'email': 'buyer@example.com'}, 'shipping_details': {'name': 'Mixed Buyer', 'address': {'city': 'New York'}}})
            session.commit()
            refresh(session, order)
            self.assertEqual(order.status.name, 'accepted')
        self.assertTrue(routes.get_gallery_item(item.id).is_sold)
        self.assertIsNone(routes.get_gallery_item(item.id).price_cents)
        self.comments('123456')
        delivered = routes.update_order_status('123456', StatusUpdateRequest(status='delivered'), self.auth)
        self.assertEqual(delivered.shipping_city, 'New York')
        self.assertIsNotNone(routes.confirm_order_received('123456').customer_confirmed_at)
        review = routes.submit_order_review('123456', ReviewRequest(rating=4, body='Lovely CASE'))
        self.assertEqual(review.review.rating, 4)
        with self.sessions() as session:
            reward = routes.get_review_for_order(session, '123456')
            reward.stripe_promotion_code_id = 'Promo_Mixed'
            session.commit()
            self.assertTrue(routes.mark_review_discount_redeemed(session, 'Promo_Mixed', inquiry.order_number))
            session.commit()
            self.assertFalse(routes.mark_review_discount_redeemed(session, 'Promo_Mixed', inquiry.order_number))
            self.assertFalse(routes.review_discount_eligible(session, 'buyer@example.com'))
        summaries = routes.list_admin_orders(1, 1, self.auth)
        self.assertEqual((summaries.total, len(summaries.items)), (2, 1))
        self.assertEqual(summaries.items[0].order_number, '123456')


if __name__ == '__main__':
    unittest.main()
