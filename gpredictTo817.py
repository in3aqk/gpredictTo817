#!/usr/bin/env python3

"""
Author  : Andreas Puschendorf, DL7OAP
Version : 001
Date    : 2020-09-01

This script is plugged between gpredict and ic9700 based on python 3.7
It is listing on port 4532 for gpredict frequencies
and it is sending frequencies and startsequences for ic9700 with icom CAT CIV commands to the serial port.

Usage:
1) select a satellite
2) start gpredit tracking

"""

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

import traceback
import socket
import sys
import icom
import time


class Satellite:
    name = ""
    mode = ""  # SSB, FM, CW
    satmode = ""  # U/V, V/U, S/U, U/U, V/V
    rit = 0


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Worker(QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress

    @pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class MainWindow(QMainWindow):
    HOST = '127.0.0.1'  # Standard loopback interface address (localhost)
    PORT_SERVER = 4532  # Port to listen on (non-privileged ports are > 1023)
    FREQUENCY_OFFSET_UPLINK = 40  # needed Uplinkfrequency shift in Hz before a correction is send to transceiver
    FREQUENCY_OFFSET_DOWNLINK = 25  # needed Downlinkfrequency shift in Hz before a correction is send to transceiver

    rit = 0  # rit to use
    last_rit = 0  # last rit which was set

    isSatelliteDuplex = True
    isDownlinkConstant = False
    isLoopActive = True

    satellites = []

    #  ####################################################

    def activateCorrectUplinkBandInMain(self, up_band):
        freq = {'U': '433000000', 'V': '145900000', 'S': '1295000000'}
        ic9700.setVFO('MAIN')
        if len(ic9700.setFrequence(freq.get(up_band))):
            ic9700.setExchange()
            ic9700.setFrequence(freq.get(up_band))

    def setStartSequenceSatellite(self, uplinkMode):

        # define uplink
        ic9700.setVFO('Main')
        ic9700.setVFO('VFOA')
        ic9700.setRitFrequence(0)
        ic9700.setRitOn(False)
        ic9700.setMode(uplinkMode)
        ic9700.setSplitOn(False)
        if uplinkMode == 'FM':
            ic9700.setAfcOn(False)
            ic9700.setToneHz('670')
            ic9700.setToneOn(True)

        # define downlink
        ic9700.setVFO('SUB')
        ic9700.setVFO('VFOA')
        ic9700.setRitOn(True)
        ic9700.setRitFrequence(int(self.rit))
        if uplinkMode == 'USB':
            ic9700.setMode('LSB')
        else:
            ic9700.setMode('USB')
        if uplinkMode == 'FM':
            ic9700.setMode('FM')
            ic9700.setToneOn(False)
            ic9700.setAfcOn(False)  # you could set it to True, but gpredict is accurate, so you don't really need AFC
            ic9700.setRitFrequence(0)
            ic9700.setRitOn(False)

    def setStartSequenceSimplex(self):

        # define uplink
        ic9700.setVFO('MAIN')
        ic9700.setVFO('VFOB')
        ic9700.setMode('FM')
        ic9700.setToneOn(False)
        ic9700.setAfcOn(False)
        ic9700.setRitFrequence(0)
        ic9700.setRitOn(False)

        # define downlink
        ic9700.setVFO('VFOA')
        ic9700.setMode('FM')
        ic9700.setToneOn(False)
        ic9700.setSplitOn(True)
        ic9700.setAfcOn(True)
        ic9700.setRitFrequence(0)
        ic9700.setRitOn(False)

    def setUplink(self, up):
        ic9700.setVFO('MAIN')
        ic9700.setFrequence(up)
        ic9700.setVFO('SUB')

    def setDownlink(self, dw):
        # ic9700.setVFO('SUB')   # if user did not activate sub manually, we can speed up here
        ic9700.setFrequence(dw)

    def setUplinkSimplex(self, up):
        if ic9700.isPttOff():
            ic9700.setVFO('VFOB')
            ic9700.setFrequence(up)
            ic9700.setVFO('VFOA')

    def setDownlinkSimplex(self, dw):
        if ic9700.isPttOff():
            ic9700.setVFO('VFOA')
            ic9700.setFrequence(dw)

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        try:
            with open('satellites.txt', 'r') as fp:
                for line in fp:
                    new_satellite = Satellite()
                    new_satellite.name = line.split(",")[0] + " " + line.split(",")[1]
                    new_satellite.mode = line.split(",")[1]
                    new_satellite.rit = line.split(",")[2]
                    new_satellite.satmode = line.split(",")[3].replace("\n", "").upper()
                    self.satellites.append(new_satellite)
        finally:
            fp.close()

        layout = QGridLayout()

        comboSatellite = QComboBox(self)
        for sat in self.satellites:
            comboSatellite.addItem(sat.name)
        comboSatellite.currentTextChanged.connect(self.on_combobox_changed)

        buttonRitUp = QPushButton("RIT +25Hz")
        buttonRitUp.pressed.connect(self.setRitUp)

        buttonRitDown = QPushButton("RIT -25Hz")
        buttonRitDown.pressed.connect(self.setRitDown)

        self.ritLabel = QLabel(self)

        layout.addWidget(comboSatellite, 0, 0)

        layout.addWidget(buttonRitUp, 1, 0)
        layout.addWidget(buttonRitDown, 1, 1)
        layout.addWidget(self.ritLabel, 1, 2)

        radiobutton = QRadioButton('Sat constant')
        radiobutton.setChecked(True)
        radiobutton.country = 'Sat constant'
        radiobutton.setToolTip('Frequency on satellite transponder will be held constant')
        radiobutton.toggled.connect(self.onRadioButtonSatelliteConstantClicked)
        layout.addWidget(radiobutton, 4, 0)

        radiobutton = QRadioButton('Downlink constant')
        radiobutton.setChecked(False)
        radiobutton.country = 'Downlink constant'
        radiobutton.setToolTip('Frequency on the downlink will be held constant')
        radiobutton.toggled.connect(self.onRadioButtonDownlinkConstantClicked)
        layout.addWidget(radiobutton, 4, 1)

        w = QWidget()
        w.setLayout(layout)

        self.setWindowTitle('gpredict and ic9700')
        self.setCentralWidget(w)
        self.show()

        self.threadpool = QThreadPool()

        worker = Worker(self.execute_main_loop)  # Any other args, kwargs are passed to the run function
        # Execute
        self.threadpool.start(worker)

    def onRadioButtonDownlinkConstantClicked(self):
        self.isDownlinkConstant = True

    def onRadioButtonSatelliteConstantClicked(self):
        self.isDownlinkConstant = False

    def on_combobox_changed(self, value):
        for sat in self.satellites:
            if sat.name == value:
                self.isLoopActive = False
                time.sleep(0.5)

                ic9700.setSatelliteMode(False)
                ic9700.setDualWatch(True)

                # set correct bands in SUB and MAIN für U/U, U/V, etc
                satModeArray = sat.satmode.split('/')
                self.activateCorrectUplinkBandInMain(satModeArray[0])
                if satModeArray[0] != satModeArray[1]:
                    self.isSatelliteDuplex = True
                else:
                    self.isSatelliteDuplex = False

                self.rit = int(sat.rit)

                if self.isSatelliteDuplex:
                    if sat.mode == 'SSB':
                        self.setStartSequenceSatellite('LSB')
                    if sat.mode == 'CW':
                        self.setStartSequenceSatellite('CW')
                    if sat.mode == 'FM':
                        self.setStartSequenceSatellite('FM')
                else:
                    self.setStartSequenceSimplex()

                self.isLoopActive = True
                break

    def execute_main_loop(self, progress_callback):
        uplink = '0'
        downlink = '0'
        last_uplink = '0'
        last_downlink = '0'

        ###############################################
        # start socket for gpredict
        ###############################################

        # start tcp server
        sock_gpredict = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock_gpredict.bind((self.HOST, self.PORT_SERVER))
        sock_gpredict.listen(1)

        ###############################################
        # main loop
        ###############################################

        while True:
            conn, addr = sock_gpredict.accept()
            print('Connected by', addr)
            while 1:
                if self.isLoopActive:
                    try:
                        data = conn.recv(1000)
                        print('\n###### LOOP START')
                        print('> gpredict: ' + data.decode('utf-8').replace('\n', ''))
                        if not data:
                            break
                        if self.rit != self.last_rit:
                            ic9700.setRitFrequence(self.rit)
                            self.last_rit = self.rit
                            self.ritLabel.setText(str(self.rit))
                        if data[0] in [70, 73]:  # I, F
                            # get downlink and uplink from gpredict
                            # and set downlink and uplink to icom
                            cut = data.decode('utf-8').split(' ')
                            if data[0] == 70:  # F - gpredict want to set Downlink
                                if self.isDownlinkConstant:
                                    downlink = last_downlink
                                else:
                                    downlink = cut[len(cut) - 1].replace('\n', '')

                            if data[0] == 73:  # I - gpredict want to set Uplink
                                uplink = cut[len(cut) - 1].replace('\n', '')
                            print('>> gp2icom: last  ^ ' + last_uplink + ' v ' + last_downlink)
                            print('>> gp2icom: fresh ^ ' + uplink + ' v ' + downlink)
                            # only if uplink or downlink changed > 0 10Hz Column, then update
                            if (abs(int(last_uplink) - int(uplink)) > self.FREQUENCY_OFFSET_UPLINK):
                                if self.isSatelliteDuplex:
                                    MainWindow.setUplink(self, uplink)
                                else:
                                    MainWindow.setUplinkSimplex(self, uplink)
                                last_uplink = uplink
                            if not self.isDownlinkConstant:
                                if (abs(int(last_downlink) - int(downlink)) > self.FREQUENCY_OFFSET_DOWNLINK):
                                    if self.isSatelliteDuplex:
                                        MainWindow.setDownlink(self, downlink)
                                    else:
                                        MainWindow.setDownlinkSimplex(self, downlink)
                                    last_downlink = downlink

                            conn.send(b'RPRT 0')  # Return Data OK to gpredict
                        elif data[0] in [102, 105]:  # i, f
                            # read downlink or uplink from icom
                            # and send it to gpredict
                            if not self.isSatelliteDuplex:
                                conn.send(b'RPRT')
                            else:
                                if data[0] == 102:  # f - gpredict ask for downlink
                                    print('>> gpredict: ask for downlink')
                                    # TODO: is getWhatFrequencyIcomSendUs working properly for 1.2 GHz? issue
                                    #  of 1t character in string?
                                    icomFrequency = ic9700.getWhatFrequencyIcomSendUs()
                                    if len(icomFrequency) > 0:
                                        actual_sub_frequency = icomFrequency
                                    else:
                                        actual_sub_frequency = downlink
                                    print('> icom:', actual_sub_frequency)
                                    downlink = actual_sub_frequency
                                    last_downlink = actual_sub_frequency
                                    print('>> icom: says ' + actual_sub_frequency)
                                    b = bytearray()
                                    b.extend(map(ord, actual_sub_frequency + '\n'))
                                    conn.send(b)
                                elif data[0] == 105:  # i - gpredict ask for uplink
                                    # we do not look for dial on uplink,
                                    # we just ignore it and send back the last uplink frequency
                                    print('>> gpredict: ask for uplink. we send ' + uplink)
                                    b = bytearray()
                                    b.extend(map(ord, uplink + '\n'))
                                    conn.send(b)
                        elif data[0] == 116:  # t ptt
                            conn.send(b'0')
                        else:
                            conn.send(b'RPRT 0')  # Return Data OK to gpredict
                    except Exception as e:
                        print(type(e))
                        print(e.args)
                        print(e)
                        print('connection maybe corrupt or failure in loop: close connection')
                        conn.close()
                        break
            print('connect closed')
            conn.close()

    def setRitUp(self):
        self.rit += 25
        self.ritLabel.setText(str(self.rit))

    def setRitDown(self):
        self.rit -= 25
        self.ritLabel.setText(str(self.rit))


ic9700 = icom.ic9700('/dev/ic9700a', '115200')
app = QApplication([])
window = MainWindow()
app.exec_()
ic9700.close()
