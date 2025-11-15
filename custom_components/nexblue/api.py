import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

class NexblueAPI:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.token = None

    async def authenticate(self):
        async with aiohttp.ClientSession() as session:
            async with session.post("https://prod-management.nexblue.com/api/account/login", json={
                "email": self.email,
                "password": self.password
            }) as resp:
                if resp.status == 200:
                    self.token = (await resp.json())["token"]
                    _LOGGER.debug("Authenticated successfully.")
                else:
                    raise Exception("Authentication failed")

    async def get_charger_data(self):
        if not self.token:
            await self.authenticate()

        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://prod-management.nexblue.com/api/chargebox", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _LOGGER.debug("Fetched charger data.")
                    return data
                raise Exception("Failed to fetch charger data")