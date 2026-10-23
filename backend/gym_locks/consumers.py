# gym_locks/consumers.py

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from gym_devices.models import GymDevice


class LockerConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):

        self.device: GymDevice = self.scope["device"]
        if self.device.device_type != GymDevice.GymDeviceType.LOCKER:
            await self.close(code=4403)
            return

        self.group_name = f"locker_{self.device.id}"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )

    async def receive_json(self, content, **kwargs):
        action = content.get("action")

        if action == "locker.status":
            # TODO: Validate and process locker controller status.
            pass

        elif content.get("type") == "command_result":
            # TODO: Validate and update the locker command status.
            pass

    async def locker_message(self, event):
        await self.send_json(event["message"])
