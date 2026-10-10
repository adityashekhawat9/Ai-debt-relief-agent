import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from services.telephony.vicidial_api import VICIdialBotClient
from core.config import get_settings


class TestVICIdialBotClient(unittest.IsolatedAsyncioTestCase):
    async def test_vicidial_bot_client_transfer_payload(self):
        client = VICIdialBotClient(
            endpoint_url="http://103.113.27.27/bot_api/AmiHangup.php",
            api_key="test_key_123"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "message": "transferred"}
        mock_response.text = '{"status": "success", "message": "transferred"}'

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            res = await client.transfer_call(
                channel="SIP/5222164738-000134c9",
                unique_id="1763445543.248139",
                comment="Transferred to sales"
            )

            mock_post.assert_called_once_with(
                "http://103.113.27.27/bot_api/AmiHangup.php",
                params={
                    "key": "test_key_123",
                    "channel": "SIP/5222164738-000134c9",
                },
                json={
                    "key": "test_key_123",
                    "UNIQUEID": "1763445543.248139",
                    "Action": "TRANSFER",
                    "Comment": "Transferred to sales",
                },
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(res["status_code"], 200)
            self.assertEqual(res["response"]["status"], "success")

        await client.close()

    async def test_vicidial_bot_client_hangup_payload(self):
        client = VICIdialBotClient(
            endpoint_url="http://103.113.27.27/bot_api/AmiHangup.php",
            api_key="test_key_123"
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "message": "hungup"}
        mock_response.text = '{"status": "success", "message": "hungup"}'

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            res = await client.hangup_call(
                channel="SIP/5222164738-000134c9",
                unique_id="1763445543.248139",
                comment="Call completed"
            )

            mock_post.assert_called_once_with(
                "http://103.113.27.27/bot_api/AmiHangup.php",
                params={
                    "key": "test_key_123",
                    "channel": "SIP/5222164738-000134c9",
                },
                json={
                    "key": "test_key_123",
                    "UNIQUEID": "1763445543.248139",
                    "Action": "HANGUP",
                    "Comment": "Call completed",
                },
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(res["status_code"], 200)
            self.assertEqual(res["response"]["status"], "success")

        await client.close()

    async def test_vicidial_bot_client_http_error_handling(self):
        client = VICIdialBotClient(
            endpoint_url="http://103.113.27.27/bot_api/AmiHangup.php",
            api_key="test_key_123"
        )

        with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectTimeout("Connection timed out")

            res = await client.hangup_call(
                channel="SIP/test",
                unique_id="123",
                comment="Timeout test"
            )

            self.assertIn("error", res)
            self.assertIn("Connection timed out", res["error"])

        await client.close()

    async def test_settings_integration(self):
        settings = get_settings()
        self.assertTrue(hasattr(settings, "VICIDIAL_BOT_API_URL"))
        self.assertTrue(hasattr(settings, "VICIDIAL_BOT_API_KEY"))
        self.assertIn("AmiHangup.php", settings.VICIDIAL_BOT_API_URL)
        self.assertEqual(settings.VICIDIAL_BOT_API_KEY, "jbti89692vc60b2o9nu7647")


if __name__ == "__main__":
    unittest.main()
