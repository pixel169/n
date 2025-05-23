import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError # For testing unique constraint

# Adjust the import path based on your project structure
# This assumes 'telegram_metatrader_app' is the root package for 'app'
from app.db.models import (
    Base, Order, add_order, update_order_status, 
    get_order_by_telegram_id, get_pending_orders, get_all_orders
)
from datetime import datetime

class TestDatabaseOperations(unittest.TestCase):

    def setUp(self):
        """Set up an in-memory SQLite database for each test."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine) # Create tables
        
        # Create a sessionmaker bound to the engine
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db: Session = self.SessionLocal() # Create a session for this test

    def tearDown(self):
        """Close the session and dispose of the engine after each test."""
        self.db.close()
        # Base.metadata.drop_all(self.engine) # Optional: drop tables if needed, usually not for in-memory
        self.engine.dispose()

    def test_add_and_get_order(self):
        """Test adding an order and retrieving it by telegram_message_id."""
        order_data_1 = {
            "telegram_message_id": "msg_add_get_001",
            "instrument": "EURUSD",
            "action": "Buy",
            "entry_range": "1.0800-1.0805",
            "tps": ["1.0820", "1.0830"],
            "sl": "1.0780",
            "volume": 0.01
        }
        
        # Add the order
        added_order = add_order(self.db, order_data_1)
        self.assertIsNotNone(added_order.id)
        self.assertEqual(added_order.telegram_message_id, "msg_add_get_001")
        self.assertEqual(added_order.instrument, "EURUSD")
        self.assertEqual(added_order.action, "Buy")
        self.assertEqual(added_order.entry_range, "1.0800-1.0805")
        self.assertAlmostEqual(added_order.parsed_entry_price, 1.0800) # Check parsed price
        self.assertEqual(added_order.tps, ["1.0820", "1.0830"])
        self.assertEqual(added_order.sl, "1.0780")
        self.assertEqual(added_order.volume, 0.01)
        self.assertEqual(added_order.status, "pending") # Default status

        # Retrieve the order
        retrieved_order = get_order_by_telegram_id(self.db, "msg_add_get_001")
        self.assertIsNotNone(retrieved_order)
        self.assertEqual(retrieved_order.id, added_order.id)
        self.assertEqual(retrieved_order.instrument, "EURUSD")

    def test_update_order_status(self):
        """Test updating an existing order's status and other fields."""
        order_data_2 = {
            "telegram_message_id": "msg_update_002",
            "instrument": "GBPUSD",
            "action": "Sell",
            "entry_range": "1.2600-1.2605",
            "volume": 0.02
        }
        added_order = add_order(self.db, order_data_2)
        self.assertIsNotNone(added_order)
        
        mt5_order_id = 12345
        new_status = "executed"
        executed_price = 1.2601
        status_message = "Order filled by MT5"

        updated_order = update_order_status(
            self.db, 
            order_id=added_order.id,
            mt5_order_id=mt5_order_id,
            status=new_status,
            executed_price=executed_price,
            status_message=status_message
        )
        self.assertIsNotNone(updated_order)
        self.assertEqual(updated_order.mt5_order_id, mt5_order_id)
        self.assertEqual(updated_order.status, new_status)
        self.assertEqual(updated_order.executed_price, executed_price)
        self.assertEqual(updated_order.status_message, status_message)
        self.assertIsNotNone(updated_order.executed_time) # Should be set on "executed"

    def test_duplicate_telegram_id(self):
        """Test that adding an order with a duplicate telegram_message_id raises IntegrityError."""
        order_data_3 = {
            "telegram_message_id": "msg_duplicate_003",
            "instrument": "AUDUSD",
            "action": "Buy",
            "entry_range": "0.6500-0.6505"
        }
        add_order(self.db, order_data_3) # Add first order

        # Attempt to add another order with the same telegram_message_id
        order_data_duplicate = {
            "telegram_message_id": "msg_duplicate_003", # Same ID
            "instrument": "AUDCAD", # Different instrument
            "action": "Sell",
            "entry_range": "0.9000-0.9005"
        }
        # The add_order function in models.py re-raises exceptions, so we expect IntegrityError here
        # due to the `unique=True` constraint on `telegram_message_id`.
        with self.assertRaises(IntegrityError):
            add_order(self.db, order_data_duplicate)
        
        # Ensure the session is still usable by rolling back the failed transaction
        self.db.rollback()


    def test_get_pending_orders(self):
        """Test retrieving orders with 'pending' status."""
        order_data_pending_1 = {
            "telegram_message_id": "msg_pending_004", "instrument": "NZDUSD", 
            "action": "Buy", "entry_range": "0.6100-0.6105", "status": "pending" # Explicitly though default
        }
        order_data_executed = {
            "telegram_message_id": "msg_exec_005", "instrument": "USDCHF", 
            "action": "Sell", "entry_range": "0.9100-0.9105" 
        } # This will be pending initially
        order_data_pending_2 = {
            "telegram_message_id": "msg_pending_006", "instrument": "EURJPY", 
            "action": "Buy", "entry_range": "160.00-160.05", "status": "pending"
        }

        add_order(self.db, order_data_pending_1)
        added_exec = add_order(self.db, order_data_executed)
        add_order(self.db, order_data_pending_2)

        # Update one order to not be pending
        update_order_status(self.db, order_id=added_exec.id, status="executed", mt5_order_id=5555)

        pending_orders = get_pending_orders(self.db)
        self.assertEqual(len(pending_orders), 2)
        pending_msg_ids = {order.telegram_message_id for order in pending_orders}
        self.assertIn("msg_pending_004", pending_msg_ids)
        self.assertIn("msg_pending_006", pending_msg_ids)
        self.assertNotIn("msg_exec_005", pending_msg_ids)

    def test_get_all_orders(self):
        """Test retrieving all orders with a limit."""
        for i in range(7):
            add_order(self.db, {
                "telegram_message_id": f"msg_all_{i:03}",
                "instrument": "TEST", "action": "Buy", "entry_range": "1-2"
            })
        
        all_orders_limit_5 = get_all_orders(self.db, limit=5)
        self.assertEqual(len(all_orders_limit_5), 5)

        all_orders_default_limit = get_all_orders(self.db) # Default limit is 100
        self.assertEqual(len(all_orders_default_limit), 7)

if __name__ == '__main__':
    unittest.main(verbosity=2)
