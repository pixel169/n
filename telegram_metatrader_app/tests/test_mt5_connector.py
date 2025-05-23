import unittest
from unittest.mock import patch, MagicMock # For mocking MT5 functions and objects

# Adjust the import path based on your project structure
from app.mt5.connector import place_order, initialize_mt5, shutdown_mt5, get_symbol_info
import MetaTrader5 as mt5 # To access mt5 constants like ORDER_TYPE_BUY, etc.

# As logger is used in mt5.connector, ensure it's available or mock it if necessary
# For unit tests, it's often better if the module can run without full logging setup,
# or we can provide a NullHandler if logs are verbose during tests.
import logging
logging.getLogger('app.mt5.connector').addHandler(logging.NullHandler())


class TestMT5Connector(unittest.TestCase):

    @patch('app.mt5.connector.mt5.initialize')
    @patch('app.mt5.connector.mt5.login')
    @patch('app.mt5.connector.mt5.account_info')
    @patch('app.mt5.connector.mt5.shutdown')
    def test_initialize_and_shutdown(self, mock_shutdown, mock_account_info, mock_login, mock_initialize):
        mock_initialize.return_value = True
        mock_login.return_value = True
        mock_account_info_obj = MagicMock(name="Test Account", balance=10000, currency="USD", server="TestServer")
        mock_account_info.return_value = mock_account_info_obj
        
        self.assertTrue(initialize_mt5("test_login", "test_pass", "test_server"))
        mock_initialize.assert_called_once()
        mock_login.assert_called_once_with("test_login", "test_pass", "test_server")
        mock_account_info.assert_called_once()

        shutdown_mt5()
        mock_shutdown.assert_called_once()

    @patch('app.mt5.connector.mt5.symbol_select') # Mock symbol_select for non-visible symbol test
    @patch('app.mt5.connector.mt5.order_send')
    @patch('app.mt5.connector.mt5.symbol_info_tick')
    @patch('app.mt5.connector.mt5.symbol_info')
    def test_place_buy_order_request(self, mock_symbol_info, mock_symbol_info_tick, mock_order_send, mock_symbol_select):
        # Setup mock for symbol_info
        mock_symbol_obj = MagicMock(visible=True, name="EURUSD") # Assume visible first
        mock_symbol_info.return_value = mock_symbol_obj
        
        mock_tick = MagicMock(ask=1.0805, bid=1.0800)
        mock_symbol_info_tick.return_value = mock_tick

        mock_order_send_result = MagicMock(retcode=mt5.TRADE_RETCODE_DONE, order=12345, price=1.0805, volume=0.1, comment="TG_BOT_ORDER")
        mock_order_send.return_value = mock_order_send_result

        instrument = "EURUSD"
        order_type = "BUY"
        volume = 0.1
        sl_price = 1.0750
        tp_price = 1.0850

        result = place_order(instrument, order_type, volume, sl=sl_price, tp=tp_price)

        mock_symbol_info.assert_called_with(instrument) # Called at least once
        mock_symbol_info_tick.assert_called_once_with(instrument)
        mock_order_send.assert_called_once()
        
        sent_request = mock_order_send.call_args[0][0]
        self.assertEqual(sent_request['action'], mt5.TRADE_ACTION_DEAL)
        self.assertEqual(sent_request['symbol'], instrument)
        self.assertEqual(sent_request['volume'], volume)
        self.assertEqual(sent_request['type'], mt5.ORDER_TYPE_BUY)
        self.assertEqual(sent_request['price'], mock_tick.ask)
        self.assertEqual(sent_request['sl'], sl_price)
        self.assertEqual(sent_request['tp'], tp_price)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['order_id'], mock_order_send_result.order)
        self.assertEqual(result['price'], mock_order_send_result.price)
        
        # Test case: symbol not visible initially
        mock_symbol_info.reset_mock()
        mock_order_send.reset_mock()
        mock_symbol_select.reset_mock()
        
        mock_symbol_obj_not_visible = MagicMock(visible=False, name="EURUSD")
        mock_symbol_obj_visible_after = MagicMock(visible=True, name="EURUSD")
        
        # mt5.symbol_info is called multiple times in this scenario
        mock_symbol_info.side_effect = [mock_symbol_obj_not_visible, mock_symbol_obj_visible_after, mock_symbol_obj_visible_after]
        mock_symbol_select.return_value = True # Successfully selected
        
        place_order(instrument, order_type, volume, sl=sl_price, tp=tp_price)
        mock_symbol_select.assert_called_once_with(instrument, True)
        self.assertEqual(mock_symbol_info.call_count, 3) # Initial check, re-fetch after select, then for tick or other info
        mock_order_send.assert_called_once() # Should still send order


    @patch('app.mt5.connector.mt5.order_send')
    @patch('app.mt5.connector.mt5.symbol_info_tick')
    @patch('app.mt5.connector.mt5.symbol_info')
    def test_place_sell_order_request(self, mock_symbol_info, mock_symbol_info_tick, mock_order_send):
        mock_symbol_obj = MagicMock(visible=True, name="GBPUSD")
        mock_symbol_info.return_value = mock_symbol_obj

        mock_tick = MagicMock(ask=1.2605, bid=1.2600)
        mock_symbol_info_tick.return_value = mock_tick

        mock_order_send_result = MagicMock(retcode=mt5.TRADE_RETCODE_DONE, order=67890, price=1.2600, volume=0.05)
        mock_order_send.return_value = mock_order_send_result

        instrument = "GBPUSD"
        order_type = "SELL"
        volume = 0.05
        sl_price = 1.2650
        tp_price = 1.2550

        result = place_order(instrument, order_type, volume, sl=sl_price, tp=tp_price)

        mock_order_send.assert_called_once()
        sent_request = mock_order_send.call_args[0][0]
        self.assertEqual(sent_request['type'], mt5.ORDER_TYPE_SELL)
        self.assertEqual(sent_request['price'], mock_tick.bid)
        self.assertEqual(sent_request['sl'], sl_price)
        self.assertEqual(sent_request['tp'], tp_price)
        self.assertIsNotNone(result)
        self.assertEqual(result['order_id'], 67890)

    @patch('app.mt5.connector.mt5.order_send')
    @patch('app.mt5.connector.mt5.symbol_info_tick')
    @patch('app.mt5.connector.mt5.symbol_info')
    def test_place_order_no_sl_tp(self, mock_symbol_info, mock_symbol_info_tick, mock_order_send):
        mock_symbol_obj = MagicMock(visible=True, name="AUDUSD")
        mock_symbol_info.return_value = mock_symbol_obj
        
        mock_tick = MagicMock(ask=0.6505, bid=0.6500)
        mock_symbol_info_tick.return_value = mock_tick

        mock_order_send_result = MagicMock(retcode=mt5.TRADE_RETCODE_DONE, order=11223, price=0.6505, volume=0.2)
        mock_order_send.return_value = mock_order_send_result

        result = place_order("AUDUSD", "BUY", 0.2, sl=None, tp=None)

        mock_order_send.assert_called_once()
        sent_request = mock_order_send.call_args[0][0]
        self.assertNotIn('sl', sent_request)
        self.assertNotIn('tp', sent_request)
        self.assertIsNotNone(result)
        self.assertEqual(result['order_id'], 11223)

    @patch('app.mt5.connector.mt5.order_send')
    @patch('app.mt5.connector.mt5.symbol_info_tick')
    @patch('app.mt5.connector.mt5.symbol_info')
    @patch('app.mt5.connector.mt5.last_error') # Mock last_error as well
    def test_order_send_failure_retcode(self, mock_last_error, mock_symbol_info, mock_symbol_info_tick, mock_order_send):
        mock_symbol_obj = MagicMock(visible=True, name="USDJPY")
        mock_symbol_info.return_value = mock_symbol_obj

        mock_tick = MagicMock(ask=150.05, bid=150.00)
        mock_symbol_info_tick.return_value = mock_tick

        mock_order_send_result = MagicMock(retcode=mt5.TRADE_RETCODE_ERROR, order=0, comment="Some MT5 error")
        mock_order_send.return_value = mock_order_send_result
        
        mock_last_error.return_value = (mt5.TRADE_RETCODE_ERROR, "Mocked MT5 Last Error Description")

        result = place_order("USDJPY", "BUY", 0.1)

        mock_order_send.assert_called_once()
        self.assertIsNotNone(result)
        self.assertIn('error', result)
        self.assertEqual(result['retcode'], mt5.TRADE_RETCODE_ERROR)
        self.assertEqual(result['comment'], "Some MT5 error")
        # Check if raw_mt5_error is populated (if applicable based on connector logic)
        self.assertEqual(result.get('raw_mt5_error'), (mt5.TRADE_RETCODE_ERROR, "Mocked MT5 Last Error Description"))


    @patch('app.mt5.connector.mt5.order_send')
    @patch('app.mt5.connector.mt5.symbol_info_tick')
    @patch('app.mt5.connector.mt5.symbol_info')
    @patch('app.mt5.connector.mt5.last_error')
    def test_order_send_returns_none(self, mock_last_error, mock_symbol_info, mock_symbol_info_tick, mock_order_send):
        mock_symbol_obj = MagicMock(visible=True, name="USDCAD")
        mock_symbol_info.return_value = mock_symbol_obj

        mock_tick = MagicMock(ask=1.3505, bid=1.3500)
        mock_symbol_info_tick.return_value = mock_tick

        mock_order_send.return_value = None # Simulate order_send returning None
        mock_last_error.return_value = (-1, "Connection failed or critical MT5 issue")

        result = place_order("USDCAD", "SELL", 0.1)
            
        mock_order_send.assert_called_once()
        self.assertIsNotNone(result)
        self.assertIn('error', result)
        self.assertEqual(result['retcode'], -1)
        self.assertEqual(result['comment'], "Connection failed or critical MT5 issue")

    @patch('app.mt5.connector.mt5.symbol_info')
    def test_get_symbol_info_success(self, mock_mt5_symbol_info):
        mock_info_obj = MagicMock(
            name="EURUSD", description="Euro vs US Dollar", ask=1.0805, bid=1.0800,
            spread=5, digits=5, point=0.00001, trade_contract_size=100000,
            trade_tick_size=0.00001, trade_tick_value=1.0, volume_min=0.01,
            volume_max=100.0, volume_step=0.01, visible=True, last=1.0802, time=1678886400
        )
        mock_mt5_symbol_info.return_value = mock_info_obj

        info = get_symbol_info("EURUSD")

        mock_mt5_symbol_info.assert_called_once_with("EURUSD")
        self.assertIsNotNone(info)
        self.assertEqual(info['name'], "EURUSD")
        self.assertEqual(info['ask'], 1.0805)
        self.assertEqual(info['point'], 0.00001) # Check one of the added fields

    @patch('app.mt5.connector.mt5.symbol_info')
    @patch('app.mt5.connector.mt5.last_error')
    def test_get_symbol_info_failure(self, mock_last_error, mock_mt5_symbol_info):
        mock_mt5_symbol_info.return_value = None
        mock_last_error.return_value = (123, "Symbol not found by MT5")

        info = get_symbol_info("UNKNOWN_SYMBOL")
            
        mock_mt5_symbol_info.assert_called_once_with("UNKNOWN_SYMBOL")
        self.assertIsNone(info)

if __name__ == '__main__':
    unittest.main(verbosity=2)
