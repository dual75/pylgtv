import asyncio
import base64
import codecs
import json
import os
import websockets
import logging

logger = logging.getLogger(__name__)

from .endpoints import *

KEY_FILE_NAME = '.pylgtv'
USER_HOME = 'HOME'
HANDSHAKE_FILE_NAME = 'handshake.json'


class PyLGTVPairException(Exception):
    def __init__(self, id, message):
        self.id = id
        self.message = message


class WebOsClient(object):
    def __init__(self, ip, key_file_path=None, timeout_connect=2, loop=None):
        """Initialize the client."""
        self.ip = ip
        self.port = 3000
        self.key_file_path = key_file_path
        self.client_key = None
        self.web_socket = None
        self.command_count = 0
        self.last_response = None
        self.timeout_connect = timeout_connect
        self.loop = loop or asyncio.get_event_loop()
        self.load_key_file()

    @staticmethod
    def _get_key_file_path():
        """Return the key file path."""
        if os.getenv(USER_HOME) is not None and os.access(os.getenv(USER_HOME),
                                                          os.W_OK):
            return os.path.join(os.getenv(USER_HOME), KEY_FILE_NAME)

        return os.path.join(os.getcwd(), KEY_FILE_NAME)

    def load_key_file(self):
        """Try to load the client key for the current ip."""
        self.client_key = None
        if self.key_file_path:
            key_file_path = self.key_file_path
        else:
            key_file_path = self._get_key_file_path()
        key_dict = {}

        logger.debug('load keyfile from %s', key_file_path);

        if os.path.isfile(key_file_path):
            with open(key_file_path, 'r') as f:
                raw_data = f.read()
                if raw_data:
                    key_dict = json.loads(raw_data)

        logger.debug('getting client_key for %s from %s', self.ip, key_file_path);
        if self.ip in key_dict:
            self.client_key = key_dict[self.ip]

    def save_key_file(self):
        """Save the current client key."""
        if self.client_key is None:
            return

        if self.key_file_path:
            key_file_path = self.key_file_path
        else:
            key_file_path = self._get_key_file_path()

        logger.debug('save keyfile to %s', key_file_path);

        with open(key_file_path, 'w+') as f:
            raw_data = f.read()
            key_dict = {}

            if raw_data:
                key_dict = json.loads(raw_data)

            key_dict[self.ip] = self.client_key

            f.write(json.dumps(key_dict))

    async def _send_register_payload(self, websocket):
        """Send the register payload."""
        file = os.path.join(os.path.dirname(__file__), HANDSHAKE_FILE_NAME)

        data = codecs.open(file, 'r', 'utf-8')
        raw_handshake = data.read()

        handshake = json.loads(raw_handshake)
        handshake['payload']['client-key'] = self.client_key

        await websocket.send(json.dumps(handshake))
        raw_response = await  websocket.recv()
        response = json.loads(raw_response)

        if response['type'] == 'response' and \
                        response['payload']['pairingType'] == 'PROMPT':
            raw_response = await websocket.recv()
            response = json.loads(raw_response)
            if response['type'] == 'registered':
                self.client_key = response['payload']['client-key']
                self.save_key_file()

    def is_registered(self):
        """Paired with the tv."""
        return self.client_key is not None

    async def register(self):
        """Register wrapper."""
        logger.debug('register on %s', "ws://{}:{}".format(self.ip, self.port))
        async with websockets.connect(
                "ws://{}:{}".format(self.ip, self.port), 
                timeout=self.timeout_connect) as websocket:

            logger.debug(
                'register websocket connected to %s', 
                "ws://{}:{}".format(self.ip, self.port))
            await self._send_register_payload(websocket)

    async def _command(self, msg):
        """Send a command to the tv."""
        logger.debug('send command to %s', "ws://{}:{}".format(self.ip, self.port))
        async with websockets.connect(
                    "ws://{}:{}".format(self.ip, self.port), 
                    timeout=self.timeout_connect
                    ) as websocket:
            logger.debug(
                'command websocket connected to %s', 
                "ws://{}:{}".format(self.ip, self.port)
            )

            await self._send_register_payload(websocket)
            if not self.client_key:
                raise PyLGTVPairException("Unable to pair")

            await websocket.send(json.dumps(msg))
            if msg['type'] == 'request':
                raw_response = await  websocket.recv()
                self.last_response = json.loads(raw_response)
    
    async def command(self, request_type, uri, payload):
        """Build and send a command."""
        self.command_count += 1

        if payload is None:
            payload = {}

        message = {
            'id': "{}_{}".format(type, self.command_count),
            'type': request_type,
            'uri': "ssap://{}".format(uri),
            'payload': payload,
        }

        self.last_response = None
        await self._command(message)

    async def request(self, uri, payload=None):
        """Send a request."""
        await self.command('request', uri, payload)

    async def send_message(self, message, icon_path=None):
        """Show a floating message."""
        icon_encoded_string = ''
        icon_extension = ''

        if icon_path is not None:
            icon_extension = os.path.splitext(icon_path)[1][1:]
            with open(icon_path, 'rb') as icon_file:
                icon_encoded_string = base64.b64encode(icon_file.read()).decode('ascii')

        await self.request(EP_SHOW_MESSAGE, {
            'message': message,
            'iconData': icon_encoded_string,
            'iconExtension': icon_extension
        })

    # Apps
    async def get_apps(self):
        """Return all apps."""
        await self.request(EP_GET_APPS)
        return {} if self.last_response is None else self.last_response.get('payload').get('launchPoints')

    async def get_current_app(self):
        """Get the current app id."""
        await self.request(EP_GET_CURRENT_APP_INFO)
        return None if self.last_response is None else self.last_response.get('payload').get('appId')

    async def launch_app(self, app):
        """Launch an app."""
        await self.command('request', EP_LAUNCH, {
            'id': app
        })

    async def launch_app_with_params(self, app, params):
        """Launch an app with parameters."""
        await self.request(EP_LAUNCH, {
            'id': app,
            'params': params
        })

    async def close_app(self, app):
        """Close the current app."""
        await self.request(EP_LAUNCHER_CLOSE, {
            'id': app
        })

    # Services
    async def get_services(self):
        """Get all services."""
        await self.request(EP_GET_SERVICES)
        return {} if self.last_response is None else self.last_response.get('payload').get('services')

    async def get_software_info(self):
        """Return the current software status."""
        await self.request(EP_GET_SOFTWARE_INFO)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def power_off(self):
        """Play media."""
        await self.request(EP_POWER_OFF)

    async def power_on(self):
        """Play media."""
        await self.request(EP_POWER_ON)

    # 3D Mode
    async def turn_3d_on(self):
        """Turn 3D on."""
        await self.request(EP_3D_ON)

    async def turn_3d_off(self):
        """Turn 3D off."""
        await self.request(EP_3D_OFF)

    # Inputs
    async def get_inputs(self):
        """Get all inputs."""
        await self.request(EP_GET_INPUTS)
        return {} if self.last_response is None else self.last_response.get('payload').get('devices')

    async def get_input(self):
        """Get current input."""
        return await self.get_current_app()

    async def set_input(self, input):
        """Set the current input."""
        await self.request(EP_SET_INPUT, {
            'inputId': input
        })

    # Audio
    async def get_audio_status(self):
        """Get the current audio status"""
        await self.request(EP_GET_AUDIO_STATUS)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def get_muted(self):
        """Get mute status."""
        status = await self.get_audio_status()
        return status.get('mute')

    async def set_mute(self, mute):
        """Set mute."""
        await self.request(EP_SET_MUTE, {
            'mute': mute
        })

    async def get_volume(self):
        """Get the current volume."""
        await self.request(EP_GET_VOLUME)
        return 0 if self.last_response is None else self.last_response.get('payload').get('volume')

    async def set_volume(self, volume):
        """Set volume."""
        volume = max(0, volume)
        await self.request(EP_SET_VOLUME, {
            'volume': volume
        })

    async def volume_up(self):
        """Volume up."""
        await self.request(EP_VOLUME_UP)

    async def volume_down(self):
        """Volume down."""
        await self.request(EP_VOLUME_DOWN)

    # TV Channel
    async def channel_up(self):
        """Channel up."""
        await self.request(EP_TV_CHANNEL_UP)

    async def channel_down(self):
        """Channel down."""
        await self.request(EP_TV_CHANNEL_DOWN)

    async def get_channels(self):
        """Get all tv channels."""
        await self.request(EP_GET_TV_CHANNELS)
        return {} if self.last_response is None else self.last_response.get('payload').get('channelList')

    async def get_current_channel(self):
        """Get the current tv channel."""
        await self.request(EP_GET_CURRENT_CHANNEL)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def get_channel_info(self):
        """Get the current channel info."""
        await self.request(EP_GET_CHANNEL_INFO)
        return {} if self.last_response is None else self.last_response.get('payload')

    async def set_channel(self, channel):
        """Set the current channel."""
        await self.request(EP_SET_CHANNEL, {
            'channelId': channel
        })

    # Media control
    async def play(self):
        """Play media."""
        await self.request(EP_MEDIA_PLAY)

    async def pause(self):
        """Pause media."""
        await self.request(EP_MEDIA_PAUSE)

    async def stop(self):
        """Stop media."""
        await self.request(EP_MEDIA_STOP)

    async def close(self):
        """Close media."""
        await self.request(EP_MEDIA_CLOSE)

    async def rewind(self):
        """Rewind media."""
        await self.request(EP_MEDIA_REWIND)

    async def fast_forward(self):
        """Fast Forward media."""
        await self.request(EP_MEDIA_FAST_FORWARD)

    # Keys
    async def send_enter_key(self):
        """Send enter key."""
        await self.request(EP_SEND_ENTER)

    async def send_delete_key(self):
        """Send delete key."""
        await self.request(EP_SEND_DELETE)

    # Web
    async def open_url(self, url):
        """Open URL."""
        await self.request(EP_OPEN, {
            'target': url
        })

    async def close_web(self):
        """Close web app."""
        await self.request(EP_CLOSE_WEB_APP)
