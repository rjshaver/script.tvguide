#
#      Copyright (C) 2012 Tommy Winther
#      http://tommy.winther.nu
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this Program; see the file LICENSE.txt.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#
import os
import datetime
import threading

import xbmc
import xbmcgui

import source as src
from notification import Notification
from strings import *
import buggalo

MODE_EPG = 1
MODE_TV = 2
MODE_OSD = 3

ACTION_LEFT = 1
ACTION_RIGHT = 2
ACTION_UP = 3
ACTION_DOWN = 4
ACTION_PAGE_UP = 5
ACTION_PAGE_DOWN = 6
ACTION_SELECT_ITEM = 7
ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_SHOW_INFO = 11
ACTION_NEXT_ITEM = 14
ACTION_PREV_ITEM = 15

ACTION_MOUSE_WHEEL_UP = 104
ACTION_MOUSE_WHEEL_DOWN = 105
ACTION_MOUSE_MOVE = 107

KEY_NAV_BACK = 92
KEY_CONTEXT_MENU = 117
KEY_HOME = 159

CHANNELS_PER_PAGE = 9

HALF_HOUR = datetime.timedelta(minutes = 30)

ADDON = xbmcaddon.Addon(id = 'script.tvguide')
TEXTURE_BUTTON_NOFOCUS = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')), 'resources', 'skins', 'Default', 'media', 'tvguide-program-grey.png')
TEXTURE_BUTTON_FOCUS = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')), 'resources', 'skins', 'Default', 'media', 'tvguide-program-grey-focus.png')
TEXTURE_BUTTON_NOFOCUS_NOTIFY = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')), 'resources', 'skins', 'Default', 'media', 'tvguide-program-red.png')
TEXTURE_BUTTON_FOCUS_NOTIFY = os.path.join(xbmc.translatePath(ADDON.getAddonInfo('path')), 'resources', 'skins', 'Default', 'media', 'tvguide-program-red-focus.png')

class SourceInitializer(threading.Thread):
    def __init__(self, sourceInitializedHandler):
        super(SourceInitializer, self).__init__()
        self.sourceInitializedHandler = sourceInitializedHandler

    def run(self):
        while not xbmc.abortRequested and not self.sourceInitializedHandler.isClosing:
            try:
                source = src.instantiateSource(ADDON, self.sourceInitializedHandler)
                xbmc.log("[script.tvguide] Using source: %s" % str(type(source)), xbmc.LOGDEBUG)
                self.sourceInitializedHandler.onSourceInitialized(source)
                break
            except src.SourceUpdateInProgressException, ex:
                xbmc.log('[script.tvguide] database update in progress...: %s' % str(ex), xbmc.LOGDEBUG)
                xbmc.sleep(1000)


class SourceUpdater(threading.Thread):
    def __init__(self, sourceUpdatedHandler, source, channelStart, startTime, scrollEvent, progressCallback):
        """

        @param sourceUpdatedHandler:
        @type sourceUpdatedHandler: TVGuide
        """
        super(SourceUpdater, self).__init__()
        self.sourceUpdatedHandler = sourceUpdatedHandler
        self.source = source
        self.channelStart = channelStart
        self.startTime = startTime
        self.scrollEvent = scrollEvent
        self.progressCallback = progressCallback

    def run(self):
        try:
            self.source.updateChannelAndProgramListCaches(self.startTime, self.progressCallback, clearExistingProgramList = False)
            self.sourceUpdatedHandler.onRedrawEPG(self.channelStart, self.startTime, self.scrollEvent, aotuFocus=True)
        except src.SourceException:
            self.sourceUpdatedHandler.onEPGLoadError()


class Point(object):
    def __init__(self):
        self.x = self.y = 0

    def __repr__(self):
        return 'Point(x=%d, y=%d)' % (self.x, self.y)

class EPGView(object):
    def __init__(self):
        self.top = self.left = self.right = self.width = self.cellHeight = 0



class TVGuide(xbmcgui.WindowXML):
    C_MAIN_DATE = 4000
    C_MAIN_TITLE = 4020
    C_MAIN_TIME = 4021
    C_MAIN_DESCRIPTION = 4022
    C_MAIN_IMAGE = 4023
    C_MAIN_LOGO = 4024
    C_MAIN_TIMEBAR = 4100
    C_MAIN_LOADING = 4200
    C_MAIN_LOADING_PROGRESS = 4201
    C_MAIN_LOADING_TIME_LEFT = 4202
    C_MAIN_LOADING_CANCEL = 4203
    C_MAIN_MOUSE_CONTROLS = 4300
    C_MAIN_MOUSE_HOME = 4301
    C_MAIN_MOUSE_LEFT = 4302
    C_MAIN_MOUSE_UP = 4303
    C_MAIN_MOUSE_DOWN = 4304
    C_MAIN_MOUSE_RIGHT = 4305
    C_MAIN_MOUSE_EXIT = 4306
    C_MAIN_BACKGROUND = 4600
    C_MAIN_EPG = 5000
    C_MAIN_EPG_VIEW_MARKER = 5001
    C_MAIN_OSD = 6000
    C_MAIN_OSD_TITLE = 6001
    C_MAIN_OSD_TIME = 6002
    C_MAIN_OSD_DESCRIPTION = 6003
    C_MAIN_OSD_CHANNEL_LOGO = 6004
    C_MAIN_OSD_CHANNEL_TITLE = 6005

    def __new__(cls):
        return super(TVGuide, cls).__new__(cls, 'script-tvguide-main.xml', ADDON.getAddonInfo('path'))

    def __init__(self):
        super(TVGuide, self).__init__()
        self.source = None
        self.notification = None
        self.redrawingEPG = False
        self.isClosing = False
        self.controlToProgramMap = dict()
        self.channelIdx = 0
        self.focusPoint = Point()
        self.epgView = EPGView()

        # add and removeControls were added post-eden
        self.hasAddControls = hasattr(self, 'addControls')
        self.hasRemoveControls = hasattr(self, 'removeControls')
        buggalo.addExtraData('hasAddControls', self.hasAddControls)
        buggalo.addExtraData('hasRemoveControls', self.hasRemoveControls)

        self.mode = MODE_EPG
        self.currentChannel = None

        self.osdChannel = None
        self.osdProgram = None

        # find nearest half hour
        self.viewStartDate = datetime.datetime.today()
        self.viewStartDate -= datetime.timedelta(minutes = self.viewStartDate.minute % 30, seconds = self.viewStartDate.second)

    def close(self):
        if not self.isClosing:
            self.isClosing = True
            if self.source:
                while self.source.updateInProgress:
                    xbmc.sleep(500)
                self.source.close()
            super(TVGuide, self).close()

    @buggalo.buggalo_try_except({'method' : 'TVGuide.onInit'})
    def onInit(self):
        self._hideControl(self.C_MAIN_MOUSE_CONTROLS)
        self._showControl(self.C_MAIN_OSD, self.C_MAIN_LOADING)
        self.getControl(self.C_MAIN_LOADING_TIME_LEFT).setLabel(strings(BACKGROUND_UPDATE_IN_PROGRESS))
        self.setFocus(self.getControl(self.C_MAIN_LOADING_CANCEL))

        control = self.getControl(self.C_MAIN_EPG_VIEW_MARKER)
        left, top = control.getPosition()
        self.focusPoint.x = left
        self.epgView.top = top
        self.epgView.left = left
        self.epgView.right = left + control.getWidth()
        self.epgView.width = control.getWidth()
        self.epgView.cellHeight = control.getHeight() / CHANNELS_PER_PAGE

        SourceInitializer(self).start()

    @buggalo.buggalo_try_except({'method' : 'TVGuide.onAction'})
    def onAction(self, action):
        if not self.source:
            if action.getId() in [ACTION_PARENT_DIR, KEY_NAV_BACK]:
                self.close()
            return

        if self.mode == MODE_TV:
            if action.getId() in [ACTION_PARENT_DIR, KEY_NAV_BACK, KEY_CONTEXT_MENU]:
                self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)

            elif action.getId() == ACTION_PAGE_UP:
                self._channelUp()

            elif action.getId() == ACTION_PAGE_DOWN:
                self._channelDown()

            elif action.getId() == ACTION_SHOW_INFO:
                self._showOsd()

        elif self.mode == MODE_OSD:
            if action.getId() == ACTION_SHOW_INFO:
                self._hideOsd()

            elif action.getId() in [ACTION_PARENT_DIR, KEY_NAV_BACK, KEY_CONTEXT_MENU]:
                self._hideOsd()
                self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)

            elif action.getId() == ACTION_SELECT_ITEM:
                if self.source.isPlayable(self.osdChannel):
                    self._playChannel(self.osdChannel)
                    self._hideOsd()

            elif action.getId() == ACTION_PAGE_UP:
                self._channelUp()
                self._showOsd()

            elif action.getId() == ACTION_PAGE_DOWN:
                self._channelDown()
                self._showOsd()

            elif action.getId() == ACTION_UP:
                self.osdChannel = self.source.getPreviousChannel(self.osdChannel)
                self.osdProgram = self.source.getCurrentProgram(self.osdChannel)
                self._showOsd()

            elif action.getId() == ACTION_DOWN:
                self.osdChannel = self.source.getNextChannel(self.osdChannel)
                self.osdProgram = self.source.getCurrentProgram(self.osdChannel)
                self._showOsd()

            elif action.getId() == ACTION_LEFT:
                previousProgram = self.source.getPreviousProgram(self.osdProgram)
                if previousProgram:
                    self.osdProgram = previousProgram
                    self._showOsd()

            elif action.getId() == ACTION_RIGHT:
                nextProgram = self.source.getNextProgram(self.osdProgram)
                if nextProgram:
                    self.osdProgram = nextProgram
                    self._showOsd()

        elif self.mode == MODE_EPG:
            if action.getId() in [ACTION_PARENT_DIR, KEY_NAV_BACK]:
                self.close()
                return

            elif action.getId() == ACTION_MOUSE_MOVE:
                self._showControl(self.C_MAIN_MOUSE_CONTROLS)
                return

            elif action.getId() == KEY_CONTEXT_MENU:
                if self.source.isPlaying():
                    self._hideEpg()

            control = None
            try:
                controlInFocus = self.getFocus()
                (left, top) = controlInFocus.getPosition()
                currentX = left + (controlInFocus.getWidth() / 2)
                currentY = top + (controlInFocus.getHeight() / 2)
            except Exception, ex:
                print str(ex)
                control = self._findControlAt(self.focusPoint.x, self.focusPoint.y)
                self.setFocus(control)
                return

            if action.getId() == ACTION_LEFT:
                control = self._left(currentX, currentY)
            elif action.getId() == ACTION_RIGHT:
                control = self._right(currentX, currentY)
            elif action.getId() == ACTION_UP:
                control = self._up(currentY)
            elif action.getId() == ACTION_DOWN:
                control = self._down(currentY)
            elif action.getId() == ACTION_NEXT_ITEM:
                control= self._nextDay( currentY)
            elif action.getId() == ACTION_PREV_ITEM:
                control= self._previousDay(currentY)
            elif action.getId() == ACTION_PAGE_UP:
                control = self._moveUp(CHANNELS_PER_PAGE)
            elif action.getId() == ACTION_PAGE_DOWN:
                control = self._moveDown(CHANNELS_PER_PAGE)
            elif action.getId() == ACTION_MOUSE_WHEEL_UP:
                self._moveUp(scrollEvent = True)
                return
            elif action.getId() == ACTION_MOUSE_WHEEL_DOWN:
                self._moveDown(scrollEvent = True)
                return
            elif action.getId() == KEY_HOME:
                self.viewStartDate = datetime.datetime.today()
                self.viewStartDate -= datetime.timedelta(minutes = self.viewStartDate.minute % 30, seconds = self.viewStartDate.second)
                self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)
            elif action.getId() in [KEY_CONTEXT_MENU, ACTION_PREVIOUS_MENU] and controlInFocus is not None:
                program = self._getProgramFromControlId(controlInFocus.getId())
                if program is not None:
                    self._showContextMenu(program)

            if control is not None:
                self.setFocus(control)

    @buggalo.buggalo_try_except({'method' : 'TVGuide.onClick'})
    def onClick(self, controlId):
        if controlId in [self.C_MAIN_LOADING_CANCEL, self.C_MAIN_MOUSE_EXIT]:
            self.close()
            return

        if self.isClosing:
            return

        if controlId == self.C_MAIN_MOUSE_HOME:
            self.viewStartDate = datetime.datetime.today()
            self.viewStartDate -= datetime.timedelta(minutes = self.viewStartDate.minute % 30, seconds = self.viewStartDate.second)
            self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)
            return
        elif controlId == self.C_MAIN_MOUSE_LEFT:
            self.viewStartDate -= datetime.timedelta(hours = 2)
            self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)
            return
        elif controlId == self.C_MAIN_MOUSE_UP:
            self._moveUp(count = CHANNELS_PER_PAGE)
            return
        elif controlId == self.C_MAIN_MOUSE_DOWN:
            self._moveDown(count = CHANNELS_PER_PAGE)
            return
        elif controlId == self.C_MAIN_MOUSE_RIGHT:
            self.viewStartDate += datetime.timedelta(hours = 2)
            self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)
            return


        program = self._getProgramFromControlId(controlId)
        if program is None:
            return

        if self.source.isPlayable(program.channel):
            self._playChannel(program.channel)
        else:
            self._showContextMenu(program)

    def _showContextMenu(self, program):
        self._hideControl(self.C_MAIN_MOUSE_CONTROLS)
        d = PopupMenu(self.source, program, not program.notificationScheduled)
        d.doModal()
        buttonClicked = d.buttonClicked
        del d

        if buttonClicked == PopupMenu.C_POPUP_REMIND:
            if program.notificationScheduled:
                self.notification.delProgram(program)
            else:
                self.notification.addProgram(program)

            self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus = True)

        elif buttonClicked == PopupMenu.C_POPUP_CHOOSE_STRM:
            filename = xbmcgui.Dialog().browse(1, ADDON.getLocalizedString(30304), 'video', '.strm')
            if filename:
                self.source.setCustomStreamUrl(program.channel, filename)

        elif buttonClicked == PopupMenu.C_POPUP_PLAY:
            if self.source.isPlayable(program.channel):
                self._playChannel(program.channel)

        elif buttonClicked == PopupMenu.C_POPUP_CHANNELS:
            d = ChannelsMenu(self.source)
            d.doModal()
            del d
            self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)

        elif buttonClicked == PopupMenu.C_POPUP_QUIT:
            self.close()

    @buggalo.buggalo_try_except({'method' : 'TVGuide.onFocus'})
    def onFocus(self, controlId):
        try:
            controlInFocus = self.getControl(controlId)
        except Exception:
            return

        program = self._getProgramFromControlId(controlId)
        if program is None:
            return

        (left, top) = controlInFocus.getPosition()
        if left > self.focusPoint.x or left + controlInFocus.getWidth() < self.focusPoint.x:
            self.focusPoint.x = left
        self.focusPoint.y = top + (controlInFocus.getHeight() / 2)

        self.getControl(self.C_MAIN_TITLE).setLabel('[B]%s[/B]' % program.title)
        self.getControl(self.C_MAIN_TIME).setLabel('[B]%s - %s[/B]' % (program.startDate.strftime(xbmc.getRegion('time')), program.endDate.strftime(xbmc.getRegion('time'))))
        self.getControl(self.C_MAIN_DESCRIPTION).setText(program.description)

        if program.channel.logo is not None:
            self.getControl(self.C_MAIN_LOGO).setImage(program.channel.logo)

        if program.imageSmall is not None:
            self.getControl(self.C_MAIN_IMAGE).setImage(program.imageSmall)

        if ADDON.getSetting('program.background.enabled') == 'true' and program.imageLarge is not None:
            self.getControl(self.C_MAIN_BACKGROUND).setImage(program.imageLarge)

    def _left(self, currentX, currentY):
        control = self._findControlOnLeft(currentX, currentY)
        if control is None:
            self.viewStartDate -= datetime.timedelta(hours = 2)
            self.onRedrawEPG(self.channelIdx, self.viewStartDate)
            control = self._findControlOnLeft(1280, currentY)

        if control is not None:
            (left, top) = control.getPosition()
            self.focusPoint.x = left
        return control

    def _right(self, currentX, currentY):
        control = self._findControlOnRight(currentX, currentY)
        if control is None:
            self.viewStartDate += datetime.timedelta(hours = 2)
            self.onRedrawEPG(self.channelIdx, self.viewStartDate)
            control = self._findControlOnRight(0, currentY)

        if control is not None:
            (left, top) = control.getPosition()
            self.focusPoint.x = left
        return control

    def _up(self, currentY):
        control = self._findControlAbove(currentY)
        if control is None:
            self.onRedrawEPG(self.channelIdx - CHANNELS_PER_PAGE, self.viewStartDate)
            control = self._findControlAbove(720)
        return control

    def _down(self, currentY):
        control = self._findControlBelow(currentY)
        if control is None:
            self.onRedrawEPG(self.channelIdx + CHANNELS_PER_PAGE, self.viewStartDate)
            control = self._findControlBelow(0)
        return control

    def _nextDay(self, currentY):
        self.viewStartDate += datetime.timedelta(days = 1)
        self.onRedrawEPG(self.channelIdx, self.viewStartDate)
        return self._findControlOnLeft(0, currentY)

    def _previousDay(self, currentY):
        self.viewStartDate -= datetime.timedelta(days = 1)
        self.onRedrawEPG(self.channelIdx, self.viewStartDate)
        return self._findControlOnLeft(1280, currentY)

    def _moveUp(self, count = 1, scrollEvent = False):
        self.onRedrawEPG(self.channelIdx - count, self.viewStartDate, scrollEvent = scrollEvent)
        if scrollEvent:
            return None
        else:
            return self._findControlAbove(720)

    def _moveDown(self, count = 1, scrollEvent = False):
        self.onRedrawEPG(self.channelIdx + count, self.viewStartDate, scrollEvent = scrollEvent)
        if scrollEvent:
            return None
        else:
            return self._findControlBelow(0)

    def _channelUp(self):
        channel = self.source.getNextChannel(self.currentChannel)
        if self.source.isPlayable(channel):
            self._playChannel(channel)

    def _channelDown(self):
        channel = self.source.getPreviousChannel(self.currentChannel)
        if self.source.isPlayable(channel):
            self._playChannel(channel)

    def _playChannel(self, channel):
        self.currentChannel = channel
        wasPlaying = self.source.isPlaying()
        self.source.play(channel)
        xbmc.sleep(1000)
        if not wasPlaying and self.source.isPlaying():
            self._hideEpg()

        self.osdProgram = self.source.getCurrentProgram(self.currentChannel)

    def _showOsd(self):
        if self.mode != MODE_OSD:
            self.osdChannel = self.currentChannel

        if self.osdProgram is not None:
            self.getControl(self.C_MAIN_OSD_TITLE).setLabel('[B]%s[/B]' % self.osdProgram.title)
            self.getControl(self.C_MAIN_OSD_TIME).setLabel('[B]%s - %s[/B]' % (self.osdProgram.startDate.strftime(xbmc.getRegion('time')), self.osdProgram.endDate.strftime(xbmc.getRegion('time'))))
            self.getControl(self.C_MAIN_OSD_DESCRIPTION).setText(self.osdProgram.description)
            self.getControl(self.C_MAIN_OSD_CHANNEL_TITLE).setLabel(self.osdChannel.title)
            if self.osdProgram.channel.logo is not None:
                self.getControl(self.C_MAIN_OSD_CHANNEL_LOGO).setImage(self.osdProgram.channel.logo)
            else:
                self.getControl(self.C_MAIN_OSD_CHANNEL_LOGO).setImage('')

        self.mode = MODE_OSD
        self._hideControl(self.C_MAIN_OSD)

    def _hideOsd(self):
        self.mode = MODE_TV
        self._showControl(self.C_MAIN_OSD)

    def _hideEpg(self):
        self._showControl(self.C_MAIN_EPG)
        self.mode = MODE_TV

        if self.hasRemoveControls:
            self.removeControls(self.controlToProgramMap.keys())
        else:
            for id in self.controlToProgramMap.keys():
                self.removeControl(self.getControl(id))
        self.controlToProgramMap.clear()

    def onRedrawEPG(self, channelStart, startTime, scrollEvent = False, autoFocus = False):
        if self.redrawingEPG or self.source.updateInProgress or self.isClosing:
            return # ignore redraw request while redrawing

        self.mode = MODE_EPG
        self._hideControl(self.C_MAIN_EPG)

        # move timebar to current time
        timeDelta = datetime.datetime.today() - self.viewStartDate
        c = self.getControl(self.C_MAIN_TIMEBAR)
        (x, y) = c.getPosition()
        c.setVisible(timeDelta.days == 0)
        c.setPosition(self._secondsToXposition(timeDelta.seconds), y)

        # show Loading screen
        self.getControl(self.C_MAIN_LOADING_TIME_LEFT).setLabel(strings(CALCULATING_REMAINING_TIME))
        self._showControl(self.C_MAIN_LOADING)
        self.setFocus(self.getControl(self.C_MAIN_LOADING_CANCEL))

        # remove existing controls
        if self.hasRemoveControls:
            self.removeControls(self.controlToProgramMap.keys())
        else:
            for controlId in self.controlToProgramMap.keys():
                self.removeControl(self.getControl(controlId))
        self.controlToProgramMap.clear()

        if self.source.isCacheExpired(startTime):
            self.redrawingEPG = False
            SourceUpdater(self, self.source, channelStart, startTime, scrollEvent, self.onSourceProgressUpdate).start()
            return

        # date and time row
        self.getControl(self.C_MAIN_DATE).setLabel(self.viewStartDate.strftime(xbmc.getRegion('dateshort')))
        for col in range(1, 5):
            self.getControl(4000 + col).setLabel(startTime.strftime(xbmc.getRegion('time')))
            startTime += HALF_HOUR

        # channels
        try:
            channels = self.source.getChannelList()
        except src.SourceException:
            self.onEPGLoadError()
            self.redrawingEPG = False
            return

        if channelStart < 0:
            channelStart = len(channels) - 1
        elif channelStart > len(channels) - 1:
            channelStart = 0

        channelEnd = channelStart + CHANNELS_PER_PAGE
        self.channelIdx = channelStart

        controlsToAdd = list()
        controls = list()
        viewChannels = channels[channelStart : channelEnd]
        try:
            programs = self.source.getProgramList(viewChannels, self.viewStartDate)
        except src.SourceException:
            self.onEPGLoadError()
            self.redrawingEPG = False
            return

        if programs is None:
            self.onEPGLoadError()
            self.redrawingEPG = False
            return

        # set channel logo or text
        channelsToShow = channels[channelStart : channelEnd]
        for idx in range(0, CHANNELS_PER_PAGE):
            if idx >= len(channelsToShow):
                self.getControl(4110 + idx).setImage('')
                self.getControl(4010 + idx).setLabel('')
            else:
                channel = channelsToShow[idx]
                self.getControl(4010 + idx).setLabel(channel.title)
                if channel.logo is not None:
                    self.getControl(4110 + idx).setImage(channel.logo)
                else:
                    self.getControl(4110 + idx).setImage('')

        for program in programs:
            idx = viewChannels.index(program.channel)

            startDelta = program.startDate - self.viewStartDate
            stopDelta = program.endDate - self.viewStartDate

            cellStart = self._secondsToXposition(startDelta.seconds)
            if startDelta.days < 0:
                cellStart = self.epgView.left
            cellWidth = self._secondsToXposition(stopDelta.seconds) - cellStart
            if cellStart + cellWidth > self.epgView.right:
                cellWidth = self.epgView.right - cellStart

            if cellWidth > 1:
                if program.notificationScheduled:
                    noFocusTexture = TEXTURE_BUTTON_NOFOCUS_NOTIFY
                    focusTexture = TEXTURE_BUTTON_FOCUS_NOTIFY
                else:
                    noFocusTexture = TEXTURE_BUTTON_NOFOCUS
                    focusTexture = TEXTURE_BUTTON_FOCUS

                if cellWidth < 25:
                    title = '' # Text will overflow outside the button if it is too narrow
                else:
                    title = program.title

                control = xbmcgui.ControlButton(
                    cellStart,
                    self.epgView.top + self.epgView.cellHeight * idx,
                    cellWidth - 2,
                    self.epgView.cellHeight - 2,
                    title,
                    noFocusTexture = noFocusTexture,
                    focusTexture = focusTexture
                )

                controlsToAdd.append([control, program])
                controls.append(control)

        # add program controls

        if self.hasAddControls:
            self.addControls(controls)

        for control, program in controlsToAdd:
            if not self.hasAddControls:
                self.addControl(control)
            self.controlToProgramMap[control.getId()] = program

        if autoFocus:
            control = self._findControlBelow(self.focusPoint.y)
            if control:
                self.setFocus(control)

        if scrollEvent:
            xbmc.sleep(100)

        self._hideControl(self.C_MAIN_LOADING)
        self.redrawingEPG = False

    def onEPGLoadError(self):
        self._hideControl(self.C_MAIN_LOADING)
        xbmcgui.Dialog().ok(strings(LOAD_ERROR_TITLE), strings(LOAD_ERROR_LINE1), strings(LOAD_ERROR_LINE2))
        self.close()

    def onSourceInitialized(self, source):
        self.source = source
        self.notification = Notification(self.source, ADDON.getAddonInfo('path'))

        self.getControl(self.C_MAIN_IMAGE).setImage('tvguide-logo-%s.png' % self.source.KEY)
        self.onRedrawEPG(0, self.viewStartDate, autoFocus=True)

    def onSourceProgressUpdate(self, percentageComplete):
        progressControl = self.getControl(self.C_MAIN_LOADING_PROGRESS)
        timeLeftControl = self.getControl(self.C_MAIN_LOADING_TIME_LEFT)
        if percentageComplete < 1:
            progressControl.setPercent(1)
            self.progressStartTime = datetime.datetime.now()
            self.progressPreviousPercentage = percentageComplete
        elif percentageComplete != self.progressPreviousPercentage:
            progressControl.setPercent(percentageComplete)
            self.progressPreviousPercentage = percentageComplete
            delta = datetime.datetime.now() - self.progressStartTime

            if percentageComplete < 20:
                timeLeftControl.setLabel(strings(CALCULATING_REMAINING_TIME))
            else:
                secondsLeft = int(delta.seconds) / float(percentageComplete) * (100.0 - percentageComplete)
                if secondsLeft > 30:
                    secondsLeft -= secondsLeft % 10
                timeLeftControl.setLabel(strings(TIME_LEFT) % secondsLeft)

        return not xbmc.abortRequested and not self.isClosing

    def onPlayBackStopped(self):
        self._hideOsd()
        self.onRedrawEPG(self.channelIdx, self.viewStartDate, autoFocus=True)

    def _secondsToXposition(self, seconds):
        return self.epgView.left + (seconds * self.epgView.width / 7200)

    def _findControlOnRight(self, currentX, currentY):
        distanceToNearest = 10000
        nearestControl = None

        for controlId in self.controlToProgramMap.keys():
            control = self.getControl(controlId)
            (left, top) = control.getPosition()
            x = left + (control.getWidth() / 2)
            y = top + (control.getHeight() / 2)

            if currentX < x and currentY == y:
                distance = abs(currentX - x)
                if distance < distanceToNearest:
                    distanceToNearest = distance
                    nearestControl = control

        return nearestControl


    def _findControlOnLeft(self, currentX, currentY):
        distanceToNearest = 10000
        nearestControl = None

        for controlId in self.controlToProgramMap.keys():
            control = self.getControl(controlId)
            (left, top) = control.getPosition()
            x = left + (control.getWidth() / 2)
            y = top + (control.getHeight() / 2)

            if currentX > x and currentY == y:
                distance = abs(currentX - x)
                if distance < distanceToNearest:
                    distanceToNearest = distance
                    nearestControl = control

        return nearestControl

    def _findControlBelow(self, currentY):
        nearestControl = None

        for controlId in self.controlToProgramMap.keys():
            control = self.getControl(controlId)
            (leftEdge, top) = control.getPosition()
            y = top + (control.getHeight() / 2)

            if currentY < y:
                rightEdge = leftEdge + control.getWidth()
                if(leftEdge <= self.focusPoint.x < rightEdge
                   and (nearestControl is None or nearestControl.getPosition()[1] > top)):
                    nearestControl = control

        return nearestControl

    def _findControlAbove(self, currentY):
        nearestControl = None

        for controlId in self.controlToProgramMap.keys():
            control = self.getControl(controlId)
            (leftEdge, top) = control.getPosition()
            y = top + (control.getHeight() / 2)

            if currentY > y:
                rightEdge = leftEdge + control.getWidth()
                if(leftEdge <= self.focusPoint.x < rightEdge
                   and (nearestControl is None or nearestControl.getPosition()[1] < top)):
                    nearestControl = control

        return nearestControl

    def _findControlAt(self, currentX, currentY):
        for controlId in self.controlToProgramMap.keys():
            control = self.getControl(controlId)
            (left, top) = control.getPosition()
            bottom = top + control.getHeight()
            right = left + control.getWidth()

            if left <= currentX <= right and  top <= currentY <= bottom:
                return control

        return None


    def _getProgramFromControlId(self, controlId):
        if self.controlToProgramMap.has_key(controlId):
            return self.controlToProgramMap[controlId]
        return None

    def _hideControl(self, *controlIds):
        """
        Visibility is inverted in skin
        """
        for controlId in controlIds:
            self.getControl(controlId).setVisible(True)

    def _showControl(self, *controlIds):
        """
        Visibility is inverted in skin
        """
        for controlId in controlIds:
            self.getControl(controlId).setVisible(False)

class PopupMenu(xbmcgui.WindowXMLDialog):
    C_POPUP_PLAY = 4000
    C_POPUP_CHOOSE_STRM = 4001
    C_POPUP_REMIND = 4002
    C_POPUP_CHANNELS = 4003
    C_POPUP_QUIT = 4004
    C_POPUP_CHANNEL_LOGO = 4100
    C_POPUP_CHANNEL_TITLE = 4101
    C_POPUP_PROGRAM_TITLE = 4102

    def __new__(cls, source, program, showRemind):
        return super(PopupMenu, cls).__new__(cls, 'script-tvguide-menu.xml', ADDON.getAddonInfo('path'))

    def __init__(self, source, program, showRemind):
        """

        @type source: source.Source
        @param program:
        @type program: source.Program
        @param showRemind:
        """
        super(PopupMenu, self).__init__()
        self.source = source
        self.program = program
        self.showRemind = showRemind
        self.buttonClicked = None

    @buggalo.buggalo_try_except({'method' : 'PopupMenu.onInit'})
    def onInit(self):
        playControl = self.getControl(self.C_POPUP_PLAY)
        remindControl = self.getControl(self.C_POPUP_REMIND)
        channelLogoControl = self.getControl(self.C_POPUP_CHANNEL_LOGO)
        channelTitleControl = self.getControl(self.C_POPUP_CHANNEL_TITLE)
        programTitleControl = self.getControl(self.C_POPUP_PROGRAM_TITLE)

        playControl.setLabel(strings(WATCH_CHANNEL, self.program.channel.title))
        if not self.source.isPlayable(self.program.channel):
            playControl.setEnabled(False)
            self.setFocusId(self.C_POPUP_CHOOSE_STRM)
        if self.source.getCustomStreamUrl(self.program.channel):
            chooseStrmControl = self.getControl(self.C_POPUP_CHOOSE_STRM)
            chooseStrmControl.setLabel(strings(REMOVE_STRM_FILE))

        if self.program.channel.logo is not None:
            channelLogoControl.setImage(self.program.channel.logo)
            channelTitleControl.setVisible(False)
        else:
            channelTitleControl.setLabel(self.program.channel.title)
            channelLogoControl.setVisible(False)

        programTitleControl.setLabel(self.program.title)

        if self.showRemind:
            remindControl.setLabel(strings(REMIND_PROGRAM))
        else:
            remindControl.setLabel(strings(DONT_REMIND_PROGRAM))

    @buggalo.buggalo_try_except({'method' : 'PopupMenu.onAction'})
    def onAction(self, action):
        if action.getId() in [ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, KEY_NAV_BACK, KEY_CONTEXT_MENU]:
            self.close()
            return

    @buggalo.buggalo_try_except({'method' : 'PopupMenu.onClick'})
    def onClick(self, controlId):
        if controlId == self.C_POPUP_CHOOSE_STRM and self.source.getCustomStreamUrl(self.program.channel):
            self.source.deleteCustomStreamUrl(self.program.channel)
            chooseStrmControl = self.getControl(self.C_POPUP_CHOOSE_STRM)
            chooseStrmControl.setLabel(strings(CHOOSE_STRM_FILE))

            if not self.source.isPlayable(self.program.channel):
                playControl = self.getControl(self.C_POPUP_PLAY)
                playControl.setEnabled(False)

        else:
            self.buttonClicked = controlId
            self.close()

    def onFocus(self, controlId):
        pass


class ChannelsMenu(xbmcgui.WindowXMLDialog):
    C_CHANNELS_LIST = 6000
    C_CHANNELS_SELECTION_VISIBLE = 6001
    C_CHANNELS_SELECTION = 6002
    C_CHANNELS_SAVE = 6003
    C_CHANNELS_CANCEL = 6004

    def __new__(cls, source):
        return super(ChannelsMenu, cls).__new__(cls, 'script-tvguide-channels.xml', ADDON.getAddonInfo('path'))

    def __init__(self, source):
        """

        @type source: source.Source
        """
        super(ChannelsMenu, self).__init__()
        self.source = source
        self.channelList = source._retrieveChannelListFromDatabase(False)

    @buggalo.buggalo_try_except({'method' : 'ChannelsMenu.onInit'})
    def onInit(self):
        self.updateChannelList()
        self.setFocusId(self.C_CHANNELS_LIST)

    @buggalo.buggalo_try_except({'method' : 'ChannelsMenu.onAction'})
    def onAction(self, action):
        if action.getId() in [ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, KEY_NAV_BACK, KEY_CONTEXT_MENU]:
            self.close()
            return

        if self.getFocusId() == self.C_CHANNELS_LIST and action.getId() == ACTION_LEFT:
            listControl = self.getControl(self.C_CHANNELS_LIST)
            idx = listControl.getSelectedPosition()
            buttonControl = self.getControl(self.C_CHANNELS_SELECTION)
            buttonControl.setLabel('[B]%s[/B]' % self.channelList[idx].title)

            self.getControl(self.C_CHANNELS_SELECTION_VISIBLE).setVisible(False)
            self.setFocusId(self.C_CHANNELS_SELECTION)

        elif self.getFocusId() == self.C_CHANNELS_SELECTION and action.getId() in [ACTION_RIGHT, ACTION_SELECT_ITEM]:
            self.getControl(self.C_CHANNELS_SELECTION_VISIBLE).setVisible(True)
            xbmc.sleep(350)
            self.setFocusId(self.C_CHANNELS_LIST)

        elif self.getFocusId() == self.C_CHANNELS_SELECTION and action.getId() == ACTION_UP:
            listControl = self.getControl(self.C_CHANNELS_LIST)
            idx = listControl.getSelectedPosition()
            self.swapChannels(idx, idx - 1)
            listControl.selectItem(idx - 1)

        elif self.getFocusId() == self.C_CHANNELS_SELECTION and action.getId() == ACTION_DOWN:
            listControl = self.getControl(self.C_CHANNELS_LIST)
            idx = listControl.getSelectedPosition()
            self.swapChannels(idx, idx + 1)
            listControl.selectItem(idx + 1)

    @buggalo.buggalo_try_except({'method' : 'ChannelsMenu.onClick'})
    def onClick(self, controlId):
        if controlId == self.C_CHANNELS_LIST:
            listControl = self.getControl(self.C_CHANNELS_LIST)
            item = listControl.getSelectedItem()
            channel = self.channelList[int(item.getProperty('idx'))]
            channel.visible = not channel.visible

            if channel.visible:
                iconImage = 'tvguide-channel-visible.png'
            else:
                iconImage = 'tvguide-channel-hidden.png'
            item.setIconImage(iconImage)

        elif controlId == self.C_CHANNELS_SAVE:
            self.source._storeChannelListInDatabase(self.channelList)
            self.close()

        elif controlId == self.C_CHANNELS_CANCEL:
            self.close()


    def onFocus(self, controlId):
        pass

    def updateChannelList(self):
        listControl = self.getControl(self.C_CHANNELS_LIST)
        listControl.reset()
        for idx, channel in enumerate(self.channelList):
            if channel.visible:
                iconImage = 'tvguide-channel-visible.png'
            else:
                iconImage = 'tvguide-channel-hidden.png'

            item = xbmcgui.ListItem('%3d. %s' % (idx+1, channel.title), iconImage = iconImage)
            item.setProperty('idx', str(idx))
            listControl.addItem(item)

    def updateListItem(self, idx, item = None):
        if item is None:
            item = xbmcgui.ListItem()
        channel = self.channelList[idx]
        item.setLabel('%3d. %s' % (idx+1, channel.title))

        if channel.visible:
            iconImage = 'tvguide-channel-visible.png'
        else:
            iconImage = 'tvguide-channel-hidden.png'
        item.setIconImage(iconImage)
        item.setProperty('idx', str(idx))

    def swapChannels(self, fromIdx, toIdx):
        c = self.channelList[fromIdx]
        self.channelList[fromIdx] = self.channelList[toIdx]
        self.channelList[toIdx] = c

        # recalculate weight
        for idx, channel in enumerate(self.channelList):
            channel.weight = idx

        listControl = self.getControl(self.C_CHANNELS_LIST)
        self.updateListItem(fromIdx, listControl.getListItem(fromIdx))
        self.updateListItem(toIdx, listControl.getListItem(toIdx))



