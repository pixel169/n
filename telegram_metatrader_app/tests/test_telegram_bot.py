import unittest
from app.telegram_bot.bot import parse_message # Ensure this path is correct

class TestTelegramMessageParser(unittest.TestCase):

    def test_valid_gold_sell_message(self):
        message_text = """
        🌟GOLD Sell - 2050.5-2051.0

        Some other text here.
        🔛TP =2048.0
        Another line.
        🔛TP =2045.5
        🔛TP =2040.0

        More text.
        ❎STOP LOSS 2055.0
        """
        message_id = 1001
        expected = {
            "telegram_message_id": message_id,
            "instrument": "GOLD",
            "action": "Sell",
            "entry_range": "2050.5-2051.0",
            "tps": ["2048.0", "2045.5", "2040.0"],
            "sl": "2055.0"
        }
        self.assertEqual(parse_message(message_text, message_id), expected)

    def test_valid_eurusd_buy_message(self):
        message_text = "🌟EURUSD Buy - 1.0850-1.0855\n🔛TP=1.0870\n❎SL 1.0830"
        message_id = 1002
        expected = {
            "telegram_message_id": message_id,
            "instrument": "EURUSD",
            "action": "Buy",
            "entry_range": "1.0850-1.0855",
            "tps": ["1.0870"],
            "sl": "1.0830"
        }
        self.assertEqual(parse_message(message_text, message_id), expected)

    def test_message_missing_sl(self):
        message_text = "🌟GBPUSD Buy - 1.2650-1.2655\n🔛TP=1.2670\n🔛TP=1.2690"
        message_id = 1003
        expected = {
            "telegram_message_id": message_id,
            "instrument": "GBPUSD",
            "action": "Buy",
            "entry_range": "1.2650-1.2655",
            "tps": ["1.2670", "1.2690"]
            # "sl" key should be absent if not found
        }
        # The current parse_message function in bot.py:
        # - Initializes parsed_data without 'sl'.
        # - If SL pattern matches, 'sl' is added.
        # - If SL pattern does not match, 'sl' key remains absent.
        self.assertEqual(parse_message(message_text, message_id), expected)


    def test_message_missing_tps(self):
        message_text = "🌟AUDCAD Sell - 0.9000-0.9005\n❎STOP LOSS 0.9020"
        message_id = 1004
        expected = {
            "telegram_message_id": message_id,
            "instrument": "AUDCAD",
            "action": "Sell",
            "entry_range": "0.9000-0.9005",
            # "tps" is initialized as an empty list. If no TPs are found,
            # current bot.py deletes the "tps" key.
            "sl": "0.9020"
        }
        # parse_message in bot.py:
        # `parsed_data: Dict[str, Any] = {"tps": [], "telegram_message_id": message_id}`
        # `if not parsed_data["tps"]: del parsed_data["tps"]`
        self.assertEqual(parse_message(message_text, message_id), expected)

    def test_message_with_multiple_tps_various_formats(self):
        message_text = """
        🌟NZDUSD Sell - 0.6100-0.6105
        🔛 TP = 0.6080
        🔛TP0.6060
        🔛 TP=0.6040
        ❎ SL 0.6125
        """
        message_id = 1005
        expected = {
            "telegram_message_id": message_id,
            "instrument": "NZDUSD",
            "action": "Sell",
            "entry_range": "0.6100-0.6105",
            "tps": ["0.6080", "0.6060", "0.6040"],
            "sl": "0.6125"
        }
        self.assertEqual(parse_message(message_text, message_id), expected)

    def test_invalid_message_format(self):
        message_text = "This is just some random text, not a trading signal."
        message_id = 1006
        # The parse_message function returns None if the main signal pattern is not found.
        self.assertIsNone(parse_message(message_text, message_id))

    def test_message_different_capitalization_for_action(self):
        message_text = "🌟USDJPY sElL - 150.00-150.05\n🔛tp=149.80\n❎stop loss 150.25"
        message_id = 1007
        expected = {
            "telegram_message_id": message_id,
            "instrument": "USDJPY",
            "action": "Sell", # Parser should normalize 'sElL' to 'Sell'
            "entry_range": "150.00-150.05",
            "tps": ["149.80"],
            "sl": "150.25"
        }
        self.assertEqual(parse_message(message_text, message_id), expected)
    
    def test_entry_range_spacing_normalization(self):
        # Standard spacing
        message_text_standard = "🌟EURCAD Buy - 1.1234-1.1236\n❎SL 1.1200"
        message_id = 1008
        parsed_standard = parse_message(message_text_standard, message_id)
        self.assertIsNotNone(parsed_standard)
        self.assertEqual(parsed_standard["entry_range"], "1.1234-1.1236")

        # Extra spacing around hyphen
        message_text_spaced = "🌟EURCAD Buy - 1.1234 - 1.1236\n❎SL 1.1200"
        # Using the same message_id for logical equivalence, though in reality they'd be different.
        parsed_spaced = parse_message(message_text_spaced, message_id) 
        self.assertIsNotNone(parsed_spaced)
        # The parser normalizes "1.1234 - 1.1236" to "1.1234-1.1236"
        self.assertEqual(parsed_spaced["entry_range"], "1.1234-1.1236")

    def test_message_only_instrument_action_entry_no_tp_sl(self):
        message_text = "🌟USDCAD Sell - 1.3500-1.3505"
        message_id = 1009
        expected = {
            "telegram_message_id": message_id,
            "instrument": "USDCAD",
            "action": "Sell",
            "entry_range": "1.3500-1.3505",
            # "tps" is deleted if empty
            # "sl" is absent
        }
        self.assertEqual(parse_message(message_text, message_id), expected)

    def test_message_with_sl_first_then_tp(self):
        # While not typical, test if parser handles order variation if patterns are independent
        message_text = """
        🌟CADCHF Buy - 0.6700-0.6705
        ❎SL 0.6680
        🔛TP =0.6725
        """
        message_id = 1010
        expected = {
            "telegram_message_id": message_id,
            "instrument": "CADCHF",
            "action": "Buy",
            "entry_range": "0.6700-0.6705",
            "tps": ["0.6725"],
            "sl": "0.6680"
        }
        self.assertEqual(parse_message(message_text, message_id), expected)

if __name__ == '__main__':
    unittest.main(verbosity=2)
