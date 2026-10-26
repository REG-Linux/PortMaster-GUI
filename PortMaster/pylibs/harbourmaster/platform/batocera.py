# SPDX-License-Identifier: MIT
#
# Batocera, REG-Linux and Knulli.

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from loguru import logger
from ..util import replace_file
from .base import PlatformBase


class PlatformBatocera(PlatformBase):
    MOVE_PM_BASH = False
    ES_NAME = "batocera-es"
    PORTMASTER_GAMELIST = True
    ## The folder in PortMaster/ whose control.txt this CFW uses.
    CONTROL_DIR = "batocera"

    BATOCERA_CONFIG_FILES = [
        "/userdata/system/knulli.conf",   # Knulli
        "/userdata/system/system.conf",   # REG-Linux, maybe?
        "/userdata/system/batocera.conf", # Batocera, Knulli
        ]
    BATOCERA_CONFIG = None

    def _move_launcher(self):
        """
        PortMaster.sh goes in `/userdata/roms/ports/`, where the frontend runs it.

        It arrives in `PortMaster/` with each PortMaster.zip; old installs used
        `MOVE_PM_BASH`, which left it in the tools dir instead.
        """
        GOOD_LOCATION = self.hm.scripts_dir / "PortMaster.sh"

        for old_location in (
                self.hm.tools_dir / "PortMaster" / "PortMaster.sh",
                self.hm.tools_dir / "PortMaster.sh"):
            try:
                if old_location.is_file():
                    logger.debug(f"Move {old_location} -> {GOOD_LOCATION}")
                    replace_file(old_location, GOOD_LOCATION)
                    old_location.unlink()

            except OSError as e:
                logger.error(f"Error during file operation: {e}")

    def portmaster_post_install(self):
        """
        Also on the first launch after an update: the update may have been installed by
        an older harbourmaster, whose portmaster_install never moved PortMaster.sh.
        """
        ## The launcher first, then its entry in the gamelist.
        self._move_launcher()
        super().portmaster_post_install()

    """
    Taken from Mikhailzrick's getInvertButtonsValue
    https://github.com/Mikhailzrick/batocera.linux/blob/43930d59a682953049c90833175c710f8f6fc018/package/batocera/core/batocera-configgen/configgen/configgen/generators/libretro/libretroConfig.py#L24
    """
    # Return value for es invertedbuttons
    def get_invert_buttons_value(self):  
        ES_SETTINGS = Path('/userdata/system/configs/emulationstation/es_settings.cfg')

        if not ES_SETTINGS.is_file():
            return False

        tree = ET.parse(str(ES_SETTINGS))

        root = tree.getroot()
        # Find the InvertButtons element and return value
        elem = root.find(".//bool[@name='InvertButtons']")

        if elem is not None:
            return elem.get('value') == 'true'

        return False  # Return False if not found 

    def batocera_settings_get(self, key, default=None):
        """
        This parses the batocera_settings files.
        """
        if self.BATOCERA_CONFIG is None:
            for config_file in self.BATOCERA_CONFIG_FILES:
                if Path(config_file).is_file():
                    self.BATOCERA_CONFIG = config_file
                    break
            else:
                self.BATOCERA_CONFIG = ""
                logger.error(f"Unable to find a suitable batocera.conf file, returning {default}")
                return default

        if self.BATOCERA_CONFIG == "":
            # Return default every time since none was found.
            return default

        with open(self.BATOCERA_CONFIG, 'r') as fh:
            for line in fh:
                line = line.strip()

                # Blank lines
                if line == '':
                    continue

                # Comments
                if line.startswith('#'):
                    continue

                # I dunno, lets just skip it.
                if '=' not in line:
                    continue

                line_key, line_value = line.split('=', 1)
                if key != line_key.strip():
                    continue

                logger.debug(f"{key}={line_value}")
                return line_value.strip()

        logger.debug(f"{key}={default} (default)")
        return default

    def loaded(self):
        self.WANT_SWAP_BUTTONS = not self.get_invert_buttons_value()
        # if self.WANT_SWAP_BUTTONS:
            # self.WANT_XBOX_FIX = not self.WANT_XBOX_FIX

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.xml'

    def first_run(self):
        self.portmaster_install([])

        REBOOT_FILE = self.hm.tools_dir / ".pugwash-reboot"
        REBOOT_FILE.touch()

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        self._move_launcher()

        TL_DIR = self.hm.tools_dir / "PortMaster"
        BC_DIR = TL_DIR / self.CONTROL_DIR

        # ACTIVATE THE CONTROL
        logger.debug(f'Copy {BC_DIR / "control.txt"} -> {TL_DIR / "control.txt"}')
        shutil.copy(BC_DIR / "control.txt", TL_DIR / "control.txt")

        TASK_SET = TL_DIR / "tasksetter"
        if TASK_SET.is_file():
            TASK_SET.unlink()

        TASK_SET.touch()


class PlatformREGLinux(PlatformBatocera):
    """
    REG-Linux: Batocera's layout (/userdata/roms/ports), but RegStation is the frontend
    and regmsgd launches games: no configgen to patch, controller mappings come in
    SDL_GAMECONTROLLERCONFIG, and RegStation picks up new ports by itself, so there
    is nothing to refresh.

    RegStation's gamelist is gamelist.json (regmsgd reads gamelist.xml only while a
    folder has no gamelist.json, and it writes one as soon as a game is played), so
    the entries go there, in its format.
    """
    ES_NAME = None
    CONTROL_DIR = "reglinux"

    ## What gamelist_backup() writes when the gamelist is missing or empty.
    BLANK_GAMELIST_XML = '{\n  "gameList": {\n    "entries": []\n  }\n}\n'

    REGSTATION_SETTINGS = Path('/userdata/system/configs/regstation/rs_settings.json')

    def get_invert_buttons_value(self):
        ## RegStation only writes the settings that differ from its defaults, and
        ## InvertButtons defaults to true.
        try:
            with open(str(self.REGSTATION_SETTINGS), 'r') as fh:
                value = json.load(fh).get('bool', {}).get('InvertButtons', True)

        except (OSError, ValueError, AttributeError):
            return True

        return value is True

    def gamelist_file(self):
        return self.hm.ports_dir / 'gamelist.json'

    def gamelist_add(self, gameinfo_file):
        """
        gameinfo.xml -> gamelist.json: { "gameList": { "entries": [ { "path", "type",
        "metadata": { key: string } } ] } }. Only the keys PortMaster knows are set;
        everything else (play counts, user edits, other entries) is kept.
        """
        if not gameinfo_file.is_file():
            return

        with self.gamelist_backup() as gamelist_json:
            if gamelist_json is None:
                return

            with open(gamelist_json, 'r', encoding='utf-8') as fh:
                data = json.load(fh)

            game_list = data.setdefault('gameList', {})
            if 'entries' not in game_list:
                ## RegStation also reads "games", but writes "entries"
                game_list['entries'] = game_list.pop('games', [])
            entries = game_list['entries']

            gameinfo_root = ET.parse(str(gameinfo_file)).getroot()
            for game in gameinfo_root.findall('game'):
                path = game.findtext('path')
                if not path:
                    continue

                entry = next((e for e in entries if isinstance(e, dict) and e.get('path') == path), None)
                if entry is None:
                    entry = {'path': path, 'type': 'game'}
                    entries.append(entry)

                logger.info(f'{path}: ')

                metadata = entry.setdefault('metadata', {})
                for child in game:
                    key = self.XML_ELEMENT_MAP.get(child.tag)
                    if key is None or key == 'path' or child.text is None:
                        continue

                    metadata[key] = child.text

                entry['metadata'] = dict(sorted(metadata.items()))

            with open(gamelist_json, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write('\n')


class PlatformKnulli(PlatformBatocera):
    WANT_XBOX_FIX = True

    def loaded(self):
        want_swap = self.batocera_settings_get('ports["PortMaster.sh"].xbox_layout', None)

        if want_swap is None:
            want_swap = self.batocera_settings_get('ports.xbox_layout', None)

        if want_swap is not None:
            self.WANT_XBOX_FIX = False
            self.WANT_SWAP_BUTTONS = want_swap == "0"

        else:
            self.WANT_SWAP_BUTTONS = not self.get_invert_buttons_value()

            if self.WANT_SWAP_BUTTONS:
                self.WANT_XBOX_FIX = not self.WANT_XBOX_FIX

    def portmaster_install(self, bash_files):
        """
        Move files into place.
        """
        super().portmaster_install(bash_files)

        TL_DIR = self.hm.tools_dir / "PortMaster"
        BC_DIR = TL_DIR / "knulli"

        # ACTIVATE THE CONTROL
        logger.debug(f'Copy {BC_DIR / "control.txt"} -> {TL_DIR / "control.txt"}')
        shutil.copy(BC_DIR / "control.txt", TL_DIR / "control.txt")

        TASK_SET = TL_DIR / "tasksetter"
        if TASK_SET.is_file():
            TASK_SET.unlink()

        TASK_SET.touch()
