from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional, Any, Dict
import re
import logging

# Get a logger instance for this module
logger = logging.getLogger(__name__)

# Define the Database URL and Engine
DATABASE_URL = "sqlite:///./telegram_metatrader_app/trading_app.db"  # DB in the project root
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}) # check_same_thread for SQLite
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the Order SQLAlchemy model
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    telegram_message_id = Column(String, unique=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    instrument = Column(String, index=True)
    action = Column(String)  # e.g., "BUY", "SELL"
    entry_range = Column(String)  # e.g., "3358-3360"
    parsed_entry_price = Column(Float, nullable=True)  # e.g., the first price from entry_range, or an average
    volume = Column(Float, default=0.01)  # Default volume, adjusted from 0.1 to common 0.01
    tps = Column(JSON, nullable=True)  # Store list of TP levels, e.g., ["3356", "3354"]
    sl = Column(String, nullable=True)  # e.g., "3365"
    mt5_order_id = Column(Integer, nullable=True, index=True)
    status = Column(String, default="pending", index=True)  # e.g., "pending", "executed", "failed", "tp_hit", "sl_hit"
    status_message = Column(String, nullable=True)  # To store error messages or other status info
    executed_price = Column(Float, nullable=True)
    executed_time = Column(DateTime, nullable=True)

    def __repr__(self):
        return (f"<Order(id={self.id}, instrument='{self.instrument}', action='{self.action}', "
                f"status='{self.status}', mt5_order_id={self.mt5_order_id})>")

# Implement create_db_and_tables() function
def create_db_and_tables():
    """
    Creates the database and all tables defined in Base.metadata.
    """
    logger.info(f"Attempting to create database and tables at {DATABASE_URL}...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database and tables created/verified successfully.")
    except Exception as e:
        logger.exception(f"Error creating database and tables at {DATABASE_URL}.")
        raise # Re-raise the exception to be handled by the caller (e.g., main.py)

# Implement add_order(db_session, order_data: dict) -> Order function
def add_order(db_session: Session, order_data: Dict[str, Any]) -> Order:
    """
    Adds a new order to the database.

    Args:
        db_session: The SQLAlchemy session.
        order_data: A dictionary containing keys like telegram_message_id, instrument,
                    action, entry_range, tps, sl, and optionally volume.
    
    Returns:
        The created Order object.
    """
    parsed_price = None
    if order_data.get("entry_range"):
        # Try to extract the first number from the entry_range string
        match = re.search(r"(\d+\.?\d*)", order_data["entry_range"])
        if match:
            try:
                parsed_price = float(match.group(1))
            except ValueError:
                logger.warning(f"Could not parse entry_price from range '{order_data['entry_range']}' for msg_id {order_data.get('telegram_message_id')}. Proceeding without parsed_price.")
                # Decide if to raise an error or proceed without parsed_price

    new_order = Order(
        telegram_message_id=str(order_data.get("telegram_message_id")), # Ensure it's a string
        instrument=order_data["instrument"],
        action=order_data["action"],
        entry_range=order_data.get("entry_range"),
        parsed_entry_price=parsed_price,
        tps=order_data.get("tps"), # This should be a list already if coming from bot.py
        sl=str(order_data.get("sl")) if order_data.get("sl") is not None else None, # Ensure SL is string or None
        volume=float(order_data.get("volume", 0.01)), # Use provided volume or default
        status="pending" # Initial status
    )
    
    try:
        db_session.add(new_order)
        db_session.commit()
        db_session.refresh(new_order)
        logger.info(f"Added order to DB: ID={new_order.id}, MsgID={new_order.telegram_message_id}, Instrument={new_order.instrument}, Action={new_order.action}")
        logger.debug(f"Full details for added order ID {new_order.id}: {new_order}")
        return new_order
    except Exception as e:
        db_session.rollback()
        logger.exception(f"Error adding order for msg_id {new_order.telegram_message_id} to database.")
        raise # Re-raise the exception to be handled by the caller

# Implement update_order_status function
def update_order_status(db_session: Session, order_id: int, 
                        mt5_order_id: Optional[int] = None, 
                        status: str, 
                        executed_price: Optional[float] = None, 
                        status_message: Optional[str] = None) -> Optional[Order]:
    """
    Updates the status and other details of an existing order.

    Args:
        db_session: The SQLAlchemy session.
        order_id: The primary key ID of the order to update.
        mt5_order_id: The MetaTrader 5 order ID, if applicable.
        status: The new status for the order.
        executed_price: The price at which the order was executed, if applicable.
        status_message: Any message related to the status update (e.g., error message).

    Returns:
        The updated Order object or None if the order is not found.
    """
    order_to_update = db_session.query(Order).filter(Order.id == order_id).first()

    if order_to_update:
        order_to_update.status = status
        if mt5_order_id is not None:
            order_to_update.mt5_order_id = mt5_order_id
        if executed_price is not None:
            order_to_update.executed_price = executed_price
        if status_message is not None:
            order_to_update.status_message = status_message
        
        if status.lower() == "executed" and order_to_update.executed_time is None: # Set time only once
            order_to_update.executed_time = datetime.utcnow()
        
        try:
            db_session.commit()
            db_session.refresh(order_to_update)
            logger.info(f"Updated order ID {order_id}: Status='{status}', MT5_ID={mt5_order_id}, ExecPrice={executed_price}")
            logger.debug(f"Full details for updated order ID {order_id}: {order_to_update}")
            return order_to_update
        except Exception as e:
            db_session.rollback()
            logger.exception(f"Error updating order ID {order_id} in database.")
            raise
    else:
        logger.warning(f"Order with id {order_id} not found for update.")
        return None

# Implement get_order_by_telegram_id function
def get_order_by_telegram_id(db_session: Session, telegram_message_id: str) -> Optional[Order]:
    """
    Fetches an order by its telegram_message_id.

    Args:
        db_session: The SQLAlchemy session.
        telegram_message_id: The Telegram message ID to search for.

    Returns:
        The Order object if found, otherwise None.
    """
    return db_session.query(Order).filter(Order.telegram_message_id == str(telegram_message_id)).first()

# Implement get_pending_orders function
def get_pending_orders(db_session: Session) -> List[Order]:
    """
    Fetches all orders with status "pending".

    Args:
        db_session: The SQLAlchemy session.

    Returns:
        A list of Order objects with status "pending".
    """
    return db_session.query(Order).filter(Order.status == "pending").all()

# Implement get_all_orders function
def get_all_orders(db_session: Session, limit: int = 100) -> List[Order]:
    """
    Fetches all orders, with a limit.

    Args:
        db_session: The SQLAlchemy session.
        limit: The maximum number of orders to return.

    Returns:
        A list of Order objects.
    """
    return db_session.query(Order).order_by(Order.timestamp.desc()).limit(limit).all()


if __name__ == '__main__':
    # Example Usage & Testing
    # For direct testing of this module, ensure logging is configured.
    if not logging.getLogger().hasHandlers(): # Check if root logger is configured
        logging.basicConfig(level=logging.DEBUG, 
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[logging.StreamHandler()])
        logger.info("Basic logging configured for db.models direct test.")

    logger.info("Running DB models example/test...")
    create_db_and_tables() # Ensure tables are created

    # Get a new session
    db = SessionLocal()

    try:
        # Test add_order
        logger.info("\n--- Testing add_order ---")
        example_signal_1 = {
            "telegram_message_id": "msg12345_test", # Using unique ID for testing
            "instrument": "GOLD",
            "action": "Sell",
            "entry_range": "2050.5-2051.0",
            "tps": ["2048.0", "2045.0"],
            "sl": "2055.0",
            "volume": 0.02
        }
        new_order_1 = None
        # Check if order already exists from a previous test run
        existing_order_1 = get_order_by_telegram_id(db, example_signal_1["telegram_message_id"])
        if existing_order_1:
            logger.info(f"Order for msg_id {example_signal_1['telegram_message_id']} already exists (ID: {existing_order_1.id}). Skipping add for test.")
            new_order_1 = existing_order_1
        else:
            new_order_1 = add_order(db, example_signal_1)
            if new_order_1:
                logger.info(f"Added order 1: ID={new_order_1.id}, Parsed Entry={new_order_1.parsed_entry_price}")

        example_signal_2 = {
            "telegram_message_id": "msg12346_test", # Different ID
            "instrument": "EURUSD",
            "action": "Buy",
            "entry_range": "1.0850", # Single price
            "tps": ["1.0870"],
            "sl": "1.0830"
            # Volume will use default 0.01
        }
        new_order_2 = None
        existing_order_2 = get_order_by_telegram_id(db, example_signal_2["telegram_message_id"])
        if existing_order_2:
            logger.info(f"Order for msg_id {example_signal_2['telegram_message_id']} already exists (ID: {existing_order_2.id}). Skipping add for test.")
            new_order_2 = existing_order_2
        else:
            new_order_2 = add_order(db, example_signal_2)
            if new_order_2:
                logger.info(f"Added order 2: ID={new_order_2.id}, Parsed Entry={new_order_2.parsed_entry_price}")

        # Test duplicate telegram_message_id (should fail or be handled by caller)
        logger.info("\n--- Testing duplicate telegram_message_id ---")
        if not existing_order_1: # Only try to add again if it wasn't pre-existing from a previous run
            try:
                add_order(db, example_signal_1) # Trying to add same msg_id again
            except Exception as e:
                logger.info(f"Correctly caught error for duplicate telegram_message_id '{example_signal_1['telegram_message_id']}': {type(e).__name__} - {e}")
                db.rollback() # Important to rollback after an exception
        else:
            logger.info(f"Skipping duplicate add test for '{example_signal_1['telegram_message_id']}' as it was pre-existing.")


        # Test get_order_by_telegram_id
        logger.info("\n--- Testing get_order_by_telegram_id ---")
        retrieved_order = get_order_by_telegram_id(db, example_signal_1["telegram_message_id"])
        if retrieved_order:
            logger.info(f"Retrieved order for {example_signal_1['telegram_message_id']}: ID={retrieved_order.id}, Status={retrieved_order.status}")
        
        retrieved_non_existent = get_order_by_telegram_id(db, "nonexistent_msg_id")
        logger.info(f"Retrieved order for 'nonexistent_msg_id': {retrieved_non_existent} (should be None)")


        # Test update_order_status
        logger.info("\n--- Testing update_order_status ---")
        if new_order_1:
            updated_order = update_order_status(db, order_id=new_order_1.id, 
                                                mt5_order_id=98765, 
                                                status="executed_test", # Using a distinct status for test
                                                executed_price=2050.6,
                                                status_message="Order filled successfully (test)")
            if updated_order:
                logger.info(f"Updated order 1: ID={updated_order.id}, Status={updated_order.status}, MT5_ID={updated_order.mt5_order_id}, ExecTime={updated_order.executed_time}")
        
        # Test update non-existent order
        updated_non_existent = update_order_status(db, order_id=999999, status="failed_non_existent")
        logger.info(f"Update non-existent order result: {updated_non_existent} (should be None)")


        # Test get_pending_orders
        logger.info("\n--- Testing get_pending_orders ---")
        pending_orders = get_pending_orders(db) # Assumes 'pending' is the default status
        logger.info(f"Pending orders ({len(pending_orders)} found):")
        for o in pending_orders:
            logger.info(f" - ID={o.id}, MsgID={o.telegram_message_id}, Status={o.status}")
        # new_order_2 (if added and not updated) might be pending

        # Test get_all_orders
        logger.info("\n--- Testing get_all_orders ---")
        all_orders = get_all_orders(db, limit=10)
        logger.info(f"All orders (limit 10, {len(all_orders)} found):")
        for o in all_orders:
            logger.info(f" - ID={o.id}, MsgID={o.telegram_message_id}, Status={o.status}, Instrument={o.instrument}")

    except Exception as e:
        logger.exception("An error occurred during DB models testing.")
    finally:
        # Close the session
        db.close()
        logger.info("Database session closed for tests.")

    logger.info("\nDB models example/test finished.")
