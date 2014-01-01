from __future__ import unicode_literals
import unittest
import datetime

import balanced
import transaction as db_transaction
from flexmock import flexmock
from freezegun import freeze_time

from billy.models.processors.base import PaymentProcessor
from billy.tests.unit.helper import ModelTestCase


class TestPaymentProcessorModel(unittest.TestCase):

    def test_base_processor(self):
        processor = PaymentProcessor()
        with self.assertRaises(NotImplementedError):
            processor.create_customer(None)
        with self.assertRaises(NotImplementedError):
            processor.prepare_customer(None)
        with self.assertRaises(NotImplementedError):
            processor.charge(None)
        with self.assertRaises(NotImplementedError):
            processor.payout(None)
        with self.assertRaises(NotImplementedError):
            processor.refund(None)


@freeze_time('2013-08-16')
class TestBalancedProcessorModel(ModelTestCase):

    def setUp(self):
        super(TestBalancedProcessorModel, self).setUp()
        # build the basic scenario for transaction model
        with db_transaction.manager:
            self.company_guid = self.company_model.create('my_secret_key')
            self.plan_guid = self.plan_model.create(
                company_guid=self.company_guid,
                plan_type=self.plan_model.TYPE_CHARGE,
                amount=10,
                frequency=self.plan_model.FREQ_MONTHLY,
            )
            self.customer_guid = self.customer_model.create(
                company_guid=self.company_guid,
                processor_uri='MOCK_BALANCED_CUSTOMER_URI',
            )
            self.subscription_guid = self.subscription_model.create(
                customer_guid=self.customer_guid,
                plan_guid=self.plan_guid,
                payment_uri='/v1/credit_card/tester',
            )
            self.invoice_guid = self.invoice_model.create(
                customer_guid=self.customer_guid,
                amount=100,
            )
        self.customer = self.customer_model.get(self.customer_guid)

    def make_one(self, *args, **kwargs):
        from billy.models.processors.balanced_payments import BalancedProcessor
        return BalancedProcessor(*args, **kwargs)

    def test_create_customer(self):
        self.customer.processor_uri = None
        # make sure API key is set correctly
        (
            flexmock(balanced)
            .should_receive('configure')
            .with_args('my_secret_key')
            .once()
        )

        # mock balanced customer instance
        mock_balanced_customer = (
            flexmock(uri='MOCK_BALANCED_CUSTOMER_URI')
            .should_receive('save')
            .replace_with(lambda: mock_balanced_customer)
            .once()
            .mock()
        )

        class BalancedCustomer(object):
            pass
        flexmock(BalancedCustomer).new_instances(mock_balanced_customer) 

        processor = self.make_one(customer_cls=BalancedCustomer)
        customer_id = processor.create_customer(self.customer)
        self.assertEqual(customer_id, 'MOCK_BALANCED_CUSTOMER_URI')

    def test_prepare_customer_with_card(self):
        # make sure API key is set correctly
        (
            flexmock(balanced)
            .should_receive('configure')
            .with_args('my_secret_key')
            .once()
        )

        # mock balanced.Customer instance
        mock_balanced_customer = (
            flexmock()
            .should_receive('add_card')
            .with_args('/v1/cards/my_card')
            .once()
            .mock()
        )

        # mock balanced.Customer class
        class BalancedCustomer(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedCustomer)
            .should_receive('find')
            .with_args('MOCK_BALANCED_CUSTOMER_URI')
            .replace_with(lambda _: mock_balanced_customer)
            .once()
        )

        processor = self.make_one(customer_cls=BalancedCustomer)
        processor.prepare_customer(self.customer, '/v1/cards/my_card')

    def test_prepare_customer_with_bank_account(self):
        # make sure API key is set correctly
        (
            flexmock(balanced)
            .should_receive('configure')
            .with_args('my_secret_key')
            .once()
        )

        # mock balanced.Customer instance
        mock_balanced_customer = (
            flexmock()
            .should_receive('add_bank_account')
            .with_args('/v1/bank_accounts/my_account')
            .once()
            .mock()
        )

        # mock balanced.Customer class
        class BalancedCustomer(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedCustomer)
            .should_receive('find')
            .with_args('MOCK_BALANCED_CUSTOMER_URI')
            .replace_with(lambda _: mock_balanced_customer)
            .once()
        )

        processor = self.make_one(customer_cls=BalancedCustomer)
        processor.prepare_customer(self.customer, '/v1/bank_accounts/my_account')

    def test_prepare_customer_with_none_payment_uri(self):
        # mock balanced.Customer instance
        mock_balanced_customer = (
            flexmock()
            .should_receive('add_bank_account')
            .never()
            .mock()
        )

        # mock balanced.Customer class
        class BalancedCustomer(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedCustomer)
            .should_receive('find')
            .with_args('MOCK_BALANCED_CUSTOMER_URI')
            .replace_with(lambda _: mock_balanced_customer)
            .never()
        )

        processor = self.make_one(customer_cls=BalancedCustomer)
        processor.prepare_customer(self.customer, None)

    def test_prepare_customer_with_bad_payment_uri(self):
        # mock balanced.Customer instance
        mock_balanced_customer = flexmock()

        # mock balanced.Customer class
        class BalancedCustomer(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedCustomer)
            .should_receive('find')
            .with_args('MOCK_BALANCED_CUSTOMER_URI')
            .replace_with(lambda _: mock_balanced_customer)
            .once()
        )

        processor = self.make_one(customer_cls=BalancedCustomer)
        with self.assertRaises(ValueError):
            processor.prepare_customer(self.customer, '/v1/bitcoin/12345')

    def _test_operation(
        self, 
        cls_name, 
        transaction_cls,
        processor_method_name, 
        api_method_name,
        extra_api_kwargs,
    ):
        tx_model = self.transaction_model
        with db_transaction.manager:
            if transaction_cls == tx_model.CLS_SUBSCRIPTION:
                guid = tx_model.create(
                    subscription_guid=self.subscription_guid,
                    transaction_cls=tx_model.CLS_SUBSCRIPTION,
                    transaction_type=tx_model.TYPE_CHARGE,
                    amount=10,
                    payment_uri='/v1/credit_card/tester',
                    appears_on_statement_as='hello baby',
                    scheduled_at=datetime.datetime.utcnow(),
                )
                transaction = tx_model.get(guid)
                description = (
                    'Generated by Billy from subscription {}, scheduled_at={}'
                    .format(
                        self.subscription_guid, 
                        transaction.scheduled_at,
                    )
                )
            elif transaction_cls == tx_model.CLS_INVOICE:
                guid = tx_model.create(
                    invoice_guid=self.invoice_guid,
                    transaction_cls=tx_model.CLS_INVOICE,
                    transaction_type=tx_model.TYPE_CHARGE,
                    amount=10,
                    payment_uri='/v1/credit_card/tester',
                    appears_on_statement_as='hello baby',
                    scheduled_at=datetime.datetime.utcnow(),
                )
                transaction = tx_model.get(guid)
                description = (
                    'Generated by Billy from invoice {}, scheduled_at={}'
                    .format(
                        self.invoice_guid, 
                        transaction.scheduled_at,
                    )
                )
            self.customer_model.update(
                guid=self.customer_guid,
                processor_uri='MOCK_BALANCED_CUSTOMER_URI',
            )
        transaction = tx_model.get(guid)

        # make sure API key is set correctly
        (
            flexmock(balanced)
            .should_receive('configure')
            .with_args('my_secret_key')
            .once()
        )

        # mock result page object of balanced.RESOURCE.query.filter(...)

        def mock_one():
            raise balanced.exc.NoResultFound

        mock_page = (
            flexmock()
            .should_receive('one')
            .replace_with(mock_one)
            .once()
            .mock()
        )

        # mock balanced.RESOURCE.query
        mock_query = (
            flexmock()
            .should_receive('filter')
            .with_args(**{'meta.billy.transaction_guid': transaction.guid})
            .replace_with(lambda **kw: mock_page)
            .mock()
        )

        # mock balanced.RESOURCE class
        class Resource(object): 
            pass
        Resource.query = mock_query

        # mock balanced.RESOURCE instance
        mock_resource = flexmock(uri='MOCK_BALANCED_RESOURCE_URI')

        # mock balanced.Customer instance
        kwargs = dict(
            amount=transaction.amount,
            meta={'billy.transaction_guid': transaction.guid},
            description=description,
            appears_on_statement_as='hello baby',
        )
        kwargs.update(extra_api_kwargs)
        mock_balanced_customer = (
            flexmock()
            .should_receive(api_method_name)
            .with_args(**kwargs)
            .replace_with(lambda **kw: mock_resource)
            .once()
            .mock()
        )

        # mock balanced.Customer class
        class BalancedCustomer(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedCustomer)
            .should_receive('find')
            .with_args('MOCK_BALANCED_CUSTOMER_URI')
            .replace_with(lambda _: mock_balanced_customer)
            .once()
        )

        processor = self.make_one(
            customer_cls=BalancedCustomer, 
            **{cls_name: Resource}
        )
        method = getattr(processor, processor_method_name)
        balanced_tx_id = method(transaction)
        self.assertEqual(balanced_tx_id, 'MOCK_BALANCED_RESOURCE_URI')

    def _test_operation_with_created_record(
        self, 
        cls_name, 
        processor_method_name,
    ):
        tx_model = self.transaction_model
        with db_transaction.manager:
            guid = tx_model.create(
                subscription_guid=self.subscription_guid,
                transaction_cls=tx_model.CLS_SUBSCRIPTION,
                transaction_type=tx_model.TYPE_CHARGE,
                amount=10,
                payment_uri='/v1/credit_card/tester',
                scheduled_at=datetime.datetime.utcnow(),
            )
            transaction = tx_model.get(guid)
        transaction = tx_model.get(guid)

        # mock balanced.RESOURCE instance
        mock_resource = flexmock(uri='MOCK_BALANCED_RESOURCE_URI')

        # mock result page object of balanced.RESOURCE.query.filter(...)
        mock_page = (
            flexmock()
            .should_receive('one')
            .replace_with(lambda: mock_resource)
            .once()
            .mock()
        )

        # mock balanced.RESOURCE.query
        mock_query = (
            flexmock()
            .should_receive('filter')
            .with_args(**{'meta.billy.transaction_guid': transaction.guid})
            .replace_with(lambda **kw: mock_page)
            .mock()
        )

        # mock balanced.RESOURCE class
        class Resource(object): 
            pass
        Resource.query = mock_query

        processor = self.make_one(**{cls_name: Resource})
        method = getattr(processor, processor_method_name)
        balanced_res_uri = method(transaction)
        self.assertEqual(balanced_res_uri, 'MOCK_BALANCED_RESOURCE_URI')

    def test_charge_subscription(self):
        self._test_operation(
            cls_name='debit_cls', 
            transaction_cls=self.transaction_model.CLS_SUBSCRIPTION,
            processor_method_name='charge',
            api_method_name='debit',
            extra_api_kwargs=dict(source_uri='/v1/credit_card/tester'),
        )

    def test_charge_invoice(self):
        self._test_operation(
            cls_name='debit_cls', 
            transaction_cls=self.transaction_model.CLS_INVOICE,
            processor_method_name='charge',
            api_method_name='debit',
            extra_api_kwargs=dict(source_uri='/v1/credit_card/tester'),
        )

    def test_charge_with_created_record(self):
        self._test_operation_with_created_record(
            cls_name='debit_cls',
            processor_method_name='charge',
        )

    def test_payout_subscription(self):
        self._test_operation(
            cls_name='credit_cls', 
            transaction_cls=self.transaction_model.CLS_SUBSCRIPTION,
            processor_method_name='payout',
            api_method_name='credit',
            extra_api_kwargs=dict(destination_uri='/v1/credit_card/tester'),
        )

    def test_payout_invoice(self):
        self._test_operation(
            cls_name='credit_cls', 
            transaction_cls=self.transaction_model.CLS_INVOICE,
            processor_method_name='payout',
            api_method_name='credit',
            extra_api_kwargs=dict(destination_uri='/v1/credit_card/tester'),
        )

    def test_payout_with_created_record(self):
        self._test_operation_with_created_record(
            cls_name='credit_cls',
            processor_method_name='payout',
        )

    def test_refund(self):
        tx_model = self.transaction_model
        with db_transaction.manager:
            charge_guid = tx_model.create(
                subscription_guid=self.subscription_guid,
                transaction_cls=tx_model.CLS_SUBSCRIPTION,
                transaction_type=tx_model.TYPE_CHARGE,
                amount=100,
                payment_uri='/v1/credit_card/tester',
                scheduled_at=datetime.datetime.utcnow(),
            )
            charge_transaction = tx_model.get(charge_guid)
            charge_transaction.status = tx_model.STATUS_DONE
            charge_transaction.external_id = 'MOCK_BALANCED_DEBIT_URI'
            self.session.add(charge_transaction)
            self.session.flush()

            refund_guid = tx_model.create(
                subscription_guid=self.subscription_guid,
                transaction_cls=tx_model.CLS_SUBSCRIPTION,
                transaction_type=tx_model.TYPE_REFUND,
                refund_to_guid=charge_guid,
                amount=56,
                scheduled_at=datetime.datetime.utcnow(),
            )

        transaction = tx_model.get(refund_guid)

        # make sure API key is set correctly
        (
            flexmock(balanced)
            .should_receive('configure')
            .with_args('my_secret_key')
            .once()
        )

        # mock result page object of balanced.Refund.query.filter(...)

        def mock_one():
            raise balanced.exc.NoResultFound

        mock_page = (
            flexmock()
            .should_receive('one')
            .replace_with(mock_one)
            .once()
            .mock()
        )

        # mock balanced.Refund.query
        mock_query = (
            flexmock()
            .should_receive('filter')
            .with_args(**{'meta.billy.transaction_guid': transaction.guid})
            .replace_with(lambda **kw: mock_page)
            .mock()
        )

        # mock balanced.Refund class
        class Refund(object): 
            pass
        Refund.query = mock_query

        # mock balanced.Refund instance
        mock_refund = flexmock(uri='MOCK_BALANCED_REFUND_URI')

        # mock balanced.Debit instance
        kwargs = dict(
            amount=transaction.amount,
            meta={'billy.transaction_guid': transaction.guid},
            description=(
                'Generated by Billy from subscription {}, scheduled_at={}'
                .format(transaction.subscription.guid, transaction.scheduled_at)
            )
        )
        mock_balanced_debit = (
            flexmock()
            .should_receive('refund')
            .with_args(**kwargs)
            .replace_with(lambda **kw: mock_refund)
            .once()
            .mock()
        )

        # mock balanced.Debit class
        class BalancedDebit(object): 
            def find(self, uri):
                pass
        (
            flexmock(BalancedDebit)
            .should_receive('find')
            .with_args('MOCK_BALANCED_DEBIT_URI')
            .replace_with(lambda _: mock_balanced_debit)
            .once()
        )

        processor = self.make_one(
            refund_cls=Refund,
            debit_cls=BalancedDebit,
        )
        refund_uri = processor.refund(transaction)
        self.assertEqual(refund_uri, 'MOCK_BALANCED_REFUND_URI')

    def test_refund_with_created_record(self):
        tx_model = self.transaction_model
        with db_transaction.manager:
            charge_guid = tx_model.create(
                subscription_guid=self.subscription_guid,
                transaction_cls=tx_model.CLS_SUBSCRIPTION,
                transaction_type=tx_model.TYPE_CHARGE,
                amount=100,
                payment_uri='/v1/credit_card/tester',
                scheduled_at=datetime.datetime.utcnow(),
            )
            charge_transaction = tx_model.get(charge_guid)
            charge_transaction.status = tx_model.STATUS_DONE
            charge_transaction.external_id = 'MOCK_BALANCED_DEBIT_URI'
            self.session.add(charge_transaction)
            self.session.flush()

            refund_guid = tx_model.create(
                subscription_guid=self.subscription_guid,
                transaction_cls=tx_model.CLS_SUBSCRIPTION,
                transaction_type=tx_model.TYPE_REFUND,
                refund_to_guid=charge_guid,
                amount=56,
                scheduled_at=datetime.datetime.utcnow(),
            )

        transaction = tx_model.get(refund_guid)

        # mock balanced.Refund instance
        mock_refund = flexmock(uri='MOCK_BALANCED_REFUND_URI')

        # mock result page object of balanced.Refund.query.filter(...)

        def mock_one():
            return mock_refund

        mock_page = (
            flexmock()
            .should_receive('one')
            .replace_with(mock_one)
            .once()
            .mock()
        )

        # mock balanced.Refund.query
        mock_query = (
            flexmock()
            .should_receive('filter')
            .with_args(**{'meta.billy.transaction_guid': transaction.guid})
            .replace_with(lambda **kw: mock_page)
            .mock()
        )

        # mock balanced.Refund class
        class Refund(object): 
            pass
        Refund.query = mock_query

        processor = self.make_one(refund_cls=Refund)
        refund_uri = processor.refund(transaction)
        self.assertEqual(refund_uri, 'MOCK_BALANCED_REFUND_URI')
