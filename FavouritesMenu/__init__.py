#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase

class ActionFavouritesMenu(InterfaceActionBase):
    name                    = 'Favourites Menu'
    description             = 'Create a customised toolbar menu button for features from other plugins or calibre menus to save screen space'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Grant Drake'
    version                 = (1, 1, 1)
    minimum_calibre_version = (2, 85, 1)

    actual_plugin           = 'calibre_plugins.favourites_menu.action:FavouritesMenuAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        if self.actual_plugin_:
            from calibre_plugins.favourites_menu.config import ConfigWidget
            return ConfigWidget(self.actual_plugin_)

    def save_settings(self, config_widget):
        config_widget.save_settings()
