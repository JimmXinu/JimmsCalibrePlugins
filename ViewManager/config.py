#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import copy, os
from functools import partial
try:
    from PyQt5 import QtWidgets as QtGui
    from PyQt5.Qt import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                          QGroupBox, QComboBox, QGridLayout, QListWidget,
                          QListWidgetItem, QIcon, QInputDialog, Qt,
                          QAction, QCheckBox, QPushButton)
except ImportError as e:
    from PyQt4 import QtGui
    from PyQt4.Qt import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                          QGroupBox, QComboBox, QGridLayout, QListWidget,
                          QListWidgetItem, QIcon, QInputDialog, Qt,
                          QAction, QCheckBox, QPushButton)
try:
    from calibre.gui2 import QVariant
    del QVariant
except ImportError:
    is_qt4 = False
    convert_qvariant = lambda x: x
else:
    is_qt4 = True
    def convert_qvariant(x):
        vt = x.type()
        if vt == x.String:
            return unicode(x.toString())
        if vt == x.List:
            return [convert_qvariant(i) for i in x.toList()]
        return x.toPyObject()

from calibre.gui2 import error_dialog, question_dialog
from calibre.utils.config import JSONConfig
from calibre.utils.icu import sort_key
from calibre.utils.search_query_parser import saved_searches

from calibre_plugins.view_manager.common_utils import (get_library_uuid, get_icon,
                                                    KeyboardConfigDialog, PrefsViewerDialog)

PREFS_NAMESPACE = 'ViewManagerPlugin'
PREFS_KEY_SETTINGS = 'settings'

# 'settings': { 'autoApplyView': False,
#               'views': { 'name':
#                             { 'sort': [],
#                               'applySearch': False,
#                               'searchToApply': '',
#                               'applyRestriction': False,
#                               'restrictionToApply': '',
#                               'columns': [ ['col1Name', col1Width], ... ]
#                             }, ...
#                        }
#               'lastView': '',
#               'viewToApply': '*last View Used'
#             }

KEY_AUTO_APPLY_VIEW = 'autoApplyView'
STORE_LIBRARIES = 'libraries'
KEY_VIEWS = 'views'
KEY_LAST_VIEW = 'lastView'
KEY_VIEW_TO_APPLY = 'viewToApply'

KEY_COLUMNS = 'columns'
KEY_SORT = 'sort'
KEY_APPLY_RESTRICTION = 'applyRestriction'
KEY_RESTRICTION = 'restrictionToApply'
KEY_APPLY_SEARCH = 'applySearch'
KEY_SEARCH = 'searchToApply'

LAST_VIEW_ITEM = '*Last View Used'

DEFAULT_LIBRARY_VALUES = {
                          KEY_VIEWS: {},
                          KEY_LAST_VIEW: '',
                          KEY_AUTO_APPLY_VIEW: False,
                          KEY_VIEW_TO_APPLY: LAST_VIEW_ITEM
                         }

KEY_SCHEMA_VERSION = 'SchemaVersion'
DEFAULT_SCHEMA_VERSION = 1.5

# This is where preferences for this plugin used to be stored prior to 1.3
plugin_prefs = JSONConfig('plugins/View Manager')

def migrate_json_config_if_required():
    # As of version 1.3 we no longer require a local json file as
    # all configuration is stored in the database
    json_path = plugin_prefs.file_path
    if not os.path.exists(json_path):
        return
    # We have to wait for all libraries to have been migrated into
    # the database. Once they have, we can nuke the json file
    if 'libraries' not in plugin_prefs:
        try:
            os.remove(json_path)
        except:
            pass


def migrate_library_config_if_required(db, library_config):
    schema_version = library_config.get(KEY_SCHEMA_VERSION, 0)
    if schema_version == DEFAULT_SCHEMA_VERSION:
        return
    # We have changes to be made - mark schema as updated
    library_config[KEY_SCHEMA_VERSION] = DEFAULT_SCHEMA_VERSION

    # Any migration code in future will exist in here.
    #if schema_version < 1.x:

    set_library_config(db, library_config)


def get_library_config(db):
    library_id = get_library_uuid(db)
    library_config = None
    # Check whether this is a view needing to be migrated from json into database
    if 'libraries' in plugin_prefs:
        libraries = plugin_prefs['libraries']
        if library_id in libraries:
            # We will migrate this below
            library_config = libraries[library_id]
            # Cleanup from json file so we don't ever do this again
            del libraries[library_id]
            if len(libraries) == 0:
                # We have migrated the last library for this user
                del plugin_prefs['libraries']
            else:
                plugin_prefs['libraries'] = libraries

    if library_config is None:
        library_config = db.prefs.get_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS,
                                                 copy.deepcopy(DEFAULT_LIBRARY_VALUES))
    migrate_library_config_if_required(db, library_config)
    return library_config

def set_library_config(db, library_config):
    db.prefs.set_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS, library_config)


class ViewComboBox(QComboBox):

    def __init__(self, parent, views, special=False):
        QComboBox.__init__(self, parent)
        self.special = special
        self.populate_combo(views)

    def populate_combo(self, views, selected_text=None):
        self.blockSignals(True)
        self.clear()
        if self.special:
            self.addItem(LAST_VIEW_ITEM)
        for view_name in sorted(views.keys()):
            self.addItem(view_name)
        self.select_view(selected_text)

    def select_view(self, selected_text):
        self.blockSignals(True)
        if selected_text:
            idx = self.findText(selected_text)
            self.setCurrentIndex(idx)
        elif self.count() > 0:
            self.setCurrentIndex(0)
        self.blockSignals(False)


class SearchComboBox(QComboBox):

    def __init__(self, parent):
        QComboBox.__init__(self, parent)
        self.populate_combo()

    def populate_combo(self):
        self.clear()
        self.addItem('')
        p = sorted(saved_searches().names(), key=sort_key)
        for search_name in p:
            self.addItem(search_name)

    def select_value(self, search):
        if search:
            idx = self.findText(search)
            self.setCurrentIndex(idx)
        elif self.count() > 0:
            self.setCurrentIndex(0)


class ColumnListWidget(QListWidget):

    def __init__(self, parent, gui):
        QListWidget.__init__(self, parent)
        self.gui = gui
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)

    def populate(self, columns, all_columns):
        self.saved_column_widths = dict(columns)
        self.all_columns_with_widths = all_columns
        self.blockSignals(True)
        self.clear()
        all_columns = [colname for colname, _width in all_columns]
        for colname, _width in columns:
            if colname in all_columns:
                all_columns.remove(colname)
                self.populate_column(colname, is_checked=True)
        if len(all_columns) > 0:
            for colname in all_columns:
                self.populate_column(colname, is_checked=False)
        self.blockSignals(False)

    def populate_column(self, colname, is_checked):
        item = QListWidgetItem(self.gui.library_view.model().headers[colname], self)
        item.setData(Qt.UserRole, colname)
        flags = Qt.ItemIsEnabled|Qt.ItemIsSelectable
        if colname != 'ondevice':
            flags |= Qt.ItemIsUserCheckable
        item.setFlags(flags)
        if colname != 'ondevice':
            item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)

    def get_data(self):
        cols = []
        for idx in xrange(self.count()):
            item = self.item(idx)
            data = convert_qvariant(item.data(Qt.UserRole)).strip()
            if item.checkState() == Qt.Checked or data == 'ondevice':
                use_width = -1
                for colname, width in self.all_columns_with_widths:
                    if colname == data:
                        use_width = width
                        break
                ## first look for previously saved width; failing
                ## that, current column size; failing that -1 default.
                cols.append((data, self.saved_column_widths.get(data,use_width)))
        return cols

    def move_column_up(self):
        idx = self.currentRow()
        if idx > 0:
            self.insertItem(idx-1, self.takeItem(idx))
            self.setCurrentRow(idx-1)

    def move_column_down(self):
        idx = self.currentRow()
        if idx < self.count()-1:
            self.insertItem(idx+1, self.takeItem(idx))
            self.setCurrentRow(idx+1)


class SortColumnListWidget(ColumnListWidget):

    def __init__(self, parent, gui):
        ColumnListWidget.__init__(self, parent, gui)
        self.create_context_menu()
        self.itemChanged.connect(self.set_sort_icon)
        self.itemSelectionChanged.connect(self.item_selection_changed)

    def create_context_menu(self):
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.sort_ascending_action = QAction('Sort ascending', self)
        self.sort_ascending_action.setIcon(get_icon('images/sort_asc.png'))
        self.sort_ascending_action.triggered.connect(partial(self.change_sort, 0))
        self.addAction(self.sort_ascending_action)
        self.sort_descending_action = QAction('Sort descending', self)
        self.sort_descending_action.setIcon(get_icon('images/sort_desc.png'))
        self.sort_descending_action.triggered.connect(partial(self.change_sort, 1))
        self.addAction(self.sort_descending_action)

    def populate(self, columns, all_columns):
        self.blockSignals(True)
        all_columns = [colname for colname, _width in all_columns]
        self.clear()
        for col, asc in columns:
            if col in all_columns:
                all_columns.remove(col)
                self.populate_column(col, asc, is_checked=True)
        if len(all_columns) > 0:
            for col in all_columns:
                self.populate_column(col, 0, is_checked=False)
        self.blockSignals(False)

    def populate_column(self, col, asc, is_checked):
        item = QListWidgetItem(self.gui.library_view.model().headers[col], self)
        item.setData(Qt.UserRole, col+'|'+str(asc))
        flags = Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable
        item.setFlags(flags)
        item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
        self.set_sort_icon(item)

    def set_sort_icon(self, item):
        previous = self.blockSignals(True)
        if item.checkState() == Qt.Checked:
            data = convert_qvariant(item.data(Qt.UserRole)).strip()
            asc = int(data.rpartition('|')[2])
            if asc == 0:
                item.setIcon(get_icon('images/sort_asc.png'))
            else:
                item.setIcon(get_icon('images/sort_desc.png'))
        else:
            item.setIcon(QIcon())
        self.item_selection_changed() ## otherwise asc/desc can be disabled if selected, then checked.
        self.blockSignals(previous)

    def item_selection_changed(self):
        self.sort_ascending_action.setEnabled(False)
        self.sort_descending_action.setEnabled(False)
        item = self.currentItem()
        if item and item.checkState() == Qt.Checked:
            self.sort_ascending_action.setEnabled(True)
            self.sort_descending_action.setEnabled(True)

    def change_sort(self, asc):
        item = self.currentItem()
        if item:
            self.blockSignals(True)
            data = convert_qvariant(item.data(Qt.UserRole)).strip().split('|')
            col = data[0]
            item.setData(Qt.UserRole, col+'|'+str(asc))
            self.set_sort_icon(item)
            self.blockSignals(False)

    def get_data(self):
        cols = []
        for idx in xrange(self.count()):
            item = self.item(idx)
            data = convert_qvariant(item.data(Qt.UserRole)).strip().split('|')
            if item.checkState() == Qt.Checked:
                cols.append((data[0], int(data[1])))
        return cols


class ConfigWidget(QWidget):

    def __init__(self, plugin_action):
        QWidget.__init__(self)
        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self.library = get_library_config(self.gui.current_db)
        self.views = self.library[KEY_VIEWS]
        self.all_columns = self.get_current_columns()
        self.view_name = None

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        select_view_layout = QHBoxLayout()
        layout.addLayout(select_view_layout)
        select_view_label = QLabel('Select view to customize:', self)
        select_view_layout.addWidget(select_view_label)
        self.select_view_combo = ViewComboBox(self, self.views)
        self.select_view_combo.setMinimumSize(150, 20)
        select_view_layout.addWidget(self.select_view_combo)
        self.add_view_button = QtGui.QToolButton(self)
        self.add_view_button.setToolTip('Add view')
        self.add_view_button.setIcon(QIcon(I('plus.png')))
        self.add_view_button.clicked.connect(self.add_view)
        select_view_layout.addWidget(self.add_view_button)
        self.delete_view_button = QtGui.QToolButton(self)
        self.delete_view_button.setToolTip('Delete view')
        self.delete_view_button.setIcon(QIcon(I('minus.png')))
        self.delete_view_button.clicked.connect(self.delete_view)
        select_view_layout.addWidget(self.delete_view_button)
        self.rename_view_button = QtGui.QToolButton(self)
        self.rename_view_button.setToolTip('Rename view')
        self.rename_view_button.setIcon(QIcon(I('edit-undo.png')))
        self.rename_view_button.clicked.connect(self.rename_view)
        select_view_layout.addWidget(self.rename_view_button)
        select_view_layout.insertStretch(-1)

        view_group_box = QGroupBox(self)
        layout.addWidget(view_group_box)
        view_group_box_layout = QVBoxLayout()
        view_group_box.setLayout(view_group_box_layout)

        customise_layout = QGridLayout()
        view_group_box_layout.addLayout(customise_layout, 1)

        self.columns_label = QLabel('Columns in view:', self)
        self.columns_list = ColumnListWidget(self, self.gui)
        self.move_column_up_button = QtGui.QToolButton(self)
        self.move_column_up_button.setToolTip('Move column up')
        self.move_column_up_button.setIcon(QIcon(I('arrow-up.png')))
        self.move_column_down_button = QtGui.QToolButton(self)
        self.move_column_down_button.setToolTip('Move column down')
        self.move_column_down_button.setIcon(QIcon(I('arrow-down.png')))
        self.move_column_up_button.clicked.connect(self.columns_list.move_column_up)
        self.move_column_down_button.clicked.connect(self.columns_list.move_column_down)

        self.sort_label = QLabel('Sort order:', self)
        self.sort_list = SortColumnListWidget(self, self.gui)
        self.move_sort_up_button = QtGui.QToolButton(self)
        self.move_sort_up_button.setToolTip('Move sort column up')
        self.move_sort_up_button.setIcon(QIcon(I('arrow-up.png')))
        self.move_sort_down_button = QtGui.QToolButton(self)
        self.move_sort_down_button.setToolTip('Move sort down')
        self.move_sort_down_button.setIcon(QIcon(I('arrow-down.png')))
        self.move_sort_up_button.clicked.connect(self.sort_list.move_column_up)
        self.move_sort_down_button.clicked.connect(self.sort_list.move_column_down)

        customise_layout.addWidget(self.columns_label, 0, 0, 1, 1)
        customise_layout.addWidget(self.sort_label, 0, 2, 1, 1)
        customise_layout.addWidget(self.columns_list, 1, 0, 3, 1)
        customise_layout.addWidget(self.move_column_up_button, 1, 1, 1, 1)
        customise_layout.addWidget(self.move_column_down_button, 3, 1, 1, 1)
        customise_layout.addWidget(self.sort_list,1, 2, 3, 1)
        customise_layout.addWidget(self.move_sort_up_button, 1, 3, 1, 1)
        customise_layout.addWidget(self.move_sort_down_button, 3, 3, 1, 1)

        self.columns_label.setMaximumHeight(self.columns_label.sizeHint().height())

        other_layout = QGridLayout()
        view_group_box_layout.addLayout(other_layout)

        self.apply_search_checkbox = QCheckBox('Apply saved &search', self)
        self.saved_search_combo = SearchComboBox(self)
        self.apply_restriction_checkbox = QCheckBox('Apply search &restriction', self)
        self.search_restriction_combo = SearchComboBox(self)

        other_layout.addWidget(self.apply_restriction_checkbox, 0, 0, 1, 1)
        other_layout.addWidget(self.search_restriction_combo, 0, 1, 1, 1)
        other_layout.addWidget(self.apply_search_checkbox, 1, 0, 1, 1)
        other_layout.addWidget(self.saved_search_combo, 1, 1, 1, 1)
        other_layout.setColumnStretch(2, 1)

        layout.addSpacing(10)
        other_group_box = QGroupBox('General Options', self)
        layout.addWidget(other_group_box)
        other_group_box_layout = QGridLayout()
        other_group_box.setLayout(other_group_box_layout)

        restart_label = QLabel('When restarting Calibre or switching to this library...')
        self.auto_apply_checkbox = QCheckBox('&Automatically apply view:', self)
        auto_apply = self.library.get(KEY_AUTO_APPLY_VIEW, False)
        self.auto_apply_checkbox.setCheckState(Qt.Checked if auto_apply else Qt.Unchecked)
        self.auto_view_combo = ViewComboBox(self, self.views, special=True)
        self.auto_view_combo.select_view(self.library.get(KEY_VIEW_TO_APPLY, LAST_VIEW_ITEM))
        self.auto_view_combo.setMinimumSize(150, 20)
        info_apply_label = QLabel('Enabling this option may override any startup search restriction or '
                                  'title sort set in Preferences -> Behaviour/Tweaks.')
        info_apply_label.setWordWrap(True)
        other_group_box_layout.addWidget(restart_label, 0, 0, 1, 2)
        other_group_box_layout.addWidget(self.auto_apply_checkbox, 1, 0, 1, 1)
        other_group_box_layout.addWidget(self.auto_view_combo, 1, 1, 1, 1)
        other_group_box_layout.addWidget(info_apply_label, 2, 0, 1, 2)
        #other_group_box.setMaximumHeight(other_group_box.sizeHint().height())

        keyboard_layout = QHBoxLayout()
        layout.addLayout(keyboard_layout)
        keyboard_shortcuts_button = QPushButton('Keyboard shortcuts...', self)
        keyboard_shortcuts_button.setToolTip(_(
                    'Edit the keyboard shortcuts associated with this plugin'))
        keyboard_shortcuts_button.clicked.connect(self.edit_shortcuts)
        view_prefs_button = QPushButton('&View library preferences...', self)
        view_prefs_button.setToolTip(_(
                    'View data stored in the library database for this plugin'))
        view_prefs_button.clicked.connect(self.view_prefs)
        keyboard_layout.addWidget(keyboard_shortcuts_button)
        keyboard_layout.addWidget(view_prefs_button)
        keyboard_layout.addStretch(1)

        # Force an initial display of view information
        if KEY_LAST_VIEW in self.library.keys():
            last_view = self.library[KEY_LAST_VIEW]
            if last_view in self.views:
                self.select_view_combo.select_view(self.library[KEY_LAST_VIEW])
        self.select_view_combo_index_changed(save_previous=False)
        self.select_view_combo.currentIndexChanged.connect(
                    partial(self.select_view_combo_index_changed, save_previous=True))

    def save_settings(self):
        # We only need to update the store for the current view, as switching views
        # will have updated the other stores
        self.persist_view_config()

        library_config = get_library_config(self.gui.current_db)
        library_config[KEY_VIEWS] = self.views
        library_config[KEY_AUTO_APPLY_VIEW] = self.auto_apply_checkbox.checkState() == Qt.Checked
        library_config[KEY_VIEW_TO_APPLY] = unicode(self.auto_view_combo.currentText())
        set_library_config(self.gui.current_db, library_config)

    def persist_view_config(self):
        if not self.view_name:
            return
        # Update all of the current user information in the store
        view_info = self.views[self.view_name]
        view_info[KEY_COLUMNS] = self.columns_list.get_data()
        view_info[KEY_SORT] = self.sort_list.get_data()
        view_info[KEY_APPLY_RESTRICTION] = self.apply_restriction_checkbox.checkState() == Qt.Checked
        if view_info[KEY_APPLY_RESTRICTION]:
            view_info[KEY_RESTRICTION] = unicode(self.search_restriction_combo.currentText()).strip()
        else:
            view_info[KEY_RESTRICTION] = ''
        view_info[KEY_APPLY_SEARCH] = self.apply_search_checkbox.checkState() == Qt.Checked
        if view_info[KEY_APPLY_SEARCH]:
            view_info[KEY_SEARCH] = unicode(self.saved_search_combo.currentText()).strip()
        else:
            view_info[KEY_SEARCH] = ''

        self.views[self.view_name] = view_info

    def select_view_combo_index_changed(self, save_previous=True):
        # Update the dialog contents with data for the selected view
        if save_previous:
            # Switching views, persist changes made to the other view
            self.persist_view_config()
        if self.select_view_combo.count() == 0:
            self.view_name = None
        else:
            self.view_name = unicode(self.select_view_combo.currentText()).strip()
        columns = []
        sort_columns = []
        all_columns = []
        apply_restriction = False
        restriction_to_apply = ''
        apply_search = False
        search_to_apply = ''
        if self.view_name:
            view_info = self.views[self.view_name]
            columns = copy.deepcopy(view_info[KEY_COLUMNS])
            sort_columns = copy.deepcopy(view_info[KEY_SORT])
            all_columns = self.all_columns
            apply_restriction = view_info[KEY_APPLY_RESTRICTION]
            restriction_to_apply = view_info[KEY_RESTRICTION]
            apply_search = view_info[KEY_APPLY_SEARCH]
            search_to_apply = view_info[KEY_SEARCH]

        self.columns_list.populate(columns, all_columns)
        self.sort_list.populate(sort_columns, all_columns)
        self.apply_restriction_checkbox.setCheckState(Qt.Checked if apply_restriction else Qt.Unchecked)
        self.search_restriction_combo.select_value(restriction_to_apply)
        self.apply_search_checkbox.setCheckState(Qt.Checked if apply_search else Qt.Unchecked)
        self.saved_search_combo.select_value(search_to_apply)

    def add_view(self):
        # Display a prompt allowing user to specify a new view
        new_view_name, ok = QInputDialog.getText(self, 'Add new view',
                    'Enter a unique display name for this view:', text='Default')
        if not ok:
            # Operation cancelled
            return
        new_view_name = unicode(new_view_name).strip()
        # Verify it does not clash with any other views in the list
        for view_name in self.views.keys():
            if view_name.lower() == new_view_name.lower():
                return error_dialog(self, 'Add Failed', 'A view with the same name already exists', show=True)

        self.persist_view_config()
        view_info = { KEY_COLUMNS: [], KEY_SORT: [],
                     KEY_APPLY_RESTRICTION: False, KEY_RESTRICTION: '',
                     KEY_APPLY_SEARCH: False, KEY_SEARCH: '' }
        if self.view_name:
            # We will copy values from the currently selected view
            old_view_info = self.views[self.view_name]
            view_info[KEY_COLUMNS] = copy.deepcopy(old_view_info[KEY_COLUMNS])
            view_info[KEY_SORT] = copy.deepcopy(old_view_info[KEY_SORT])
            view_info[KEY_APPLY_RESTRICTION] = copy.deepcopy(old_view_info[KEY_APPLY_RESTRICTION])
            view_info[KEY_RESTRICTION] = copy.deepcopy(old_view_info[KEY_RESTRICTION])
            view_info[KEY_APPLY_SEARCH] = copy.deepcopy(old_view_info[KEY_APPLY_SEARCH])
            view_info[KEY_SEARCH] = copy.deepcopy(old_view_info[KEY_SEARCH])
        else:
            # We will copy values from the current library view
            view_info[KEY_COLUMNS] = self.get_current_columns(visible_only=True)

        self.view_name = new_view_name
        self.views[new_view_name] = view_info
        # Now update the views combobox
        self.select_view_combo.populate_combo(self.views, new_view_name)
        self.select_view_combo_index_changed(save_previous=False)
        self.auto_view_combo.populate_combo(self.views, unicode(self.auto_view_combo.currentText()))

    def rename_view(self):
        if not self.view_name:
            return
        # Display a prompt allowing user to specify a rename view
        old_view_name = self.view_name
        new_view_name, ok = QInputDialog.getText(self, 'Rename view',
                    'Enter a new display name for this view:', text=old_view_name)
        if not ok:
            # Operation cancelled
            return
        new_view_name = unicode(new_view_name).strip()
        if new_view_name == old_view_name:
            return
        # Verify it does not clash with any other views in the list
        for view_name in self.views.keys():
            if view_name == old_view_name:
                continue
            if view_name.lower() == new_view_name.lower():
                return error_dialog(self, 'Add Failed', 'A view with the same name already exists', show=True)

        # Ensure any changes are persisted
        self.persist_view_config()
        view_info = self.views[old_view_name]
        del self.views[old_view_name]
        self.view_name = new_view_name
        self.views[new_view_name] = view_info
        # Now update the views combobox
        self.select_view_combo.populate_combo(self.views, new_view_name)
        self.select_view_combo_index_changed(save_previous=False)
        if unicode(self.auto_view_combo.currentText()) == old_view_name:
            self.auto_view_combo.populate_combo(self.views, new_view_name)
        else:
            self.auto_view_combo.populate_combo(self.views)

    def delete_view(self):
        if not self.view_name:
            return
        if not question_dialog(self, _('Are you sure?'), '<p>'+
                'Do you want to delete the view named \'%s\''%self.view_name,
                show_copy_button=False):
            return
        del self.views[self.view_name]
        # Now update the views combobox
        self.select_view_combo.populate_combo(self.views)
        self.select_view_combo_index_changed(save_previous=False)
        self.auto_view_combo.populate_combo(self.views)

    def get_current_columns(self, defaults=False, visible_only=False):
        model = self.gui.library_view.model()
        colmap = list(model.column_map)
        state = self.columns_state(defaults)
        positions = state['column_positions']
        colmap.sort(cmp=lambda x,y: cmp(positions[x], positions[y]))
        hidden_cols = state['hidden_columns']
        if visible_only:
            colmap = [col for col in colmap if col not in hidden_cols or col == 'ondevice']
        # Convert our list of column names into a list of tuples with column widths
        colsizemap = []
        for col in colmap:
            if col in hidden_cols:
                colsizemap.append((col, -1))
            else:
                colsizemap.append((col, state['column_sizes'].get(col,-1)))
        return colsizemap

    def columns_state(self, defaults=False):
        if defaults:
            return self.gui.library_view.get_default_state()
        return self.gui.library_view.get_state()

    def edit_shortcuts(self):
        self.save_settings()
        # Force the menus to be rebuilt immediately, so we have all our actions registered
        self.plugin_action.rebuild_menus()
        d = KeyboardConfigDialog(self.plugin_action.gui, self.plugin_action.action_spec[0])
        if d.exec_() == d.Accepted:
            self.plugin_action.gui.keyboard.finalize()

    def view_prefs(self):
        d = PrefsViewerDialog(self.plugin_action.gui, PREFS_NAMESPACE)
        d.exec_()


# Ensure our config gets migrated
migrate_json_config_if_required()