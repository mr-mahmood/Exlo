# gym_visits/consumers.py

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from gym_devices.models import GymDevice


class GateConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):

        self.device: GymDevice = self.scope["device"]  # type: ignore
        if self.device.device_type != GymDevice.GymDeviceType.ENTRANCE:
            await self.close(code=4403)
            return

        self.group_name = f"gate_{self.device.id}"
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

        if action == "nfc.scanned":
            # TODO: Validate the card and process check-in.
            pass

        elif content.get("type") == "command_result":
            # TODO: Validate and update the gate command status.
            pass

    async def gate_message(self, event):
        await self.send_json(event["message"])
