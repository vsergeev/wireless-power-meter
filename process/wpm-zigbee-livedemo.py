import os
import termios
import sys
import signal
import time
import struct
import serial
import threading
import copy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Subplot
from matplotlib.backends.backend_gtkagg import FigureCanvasGTK
from matplotlib import pylab
import pygtk
import gtk
import gtk.glade
import gobject

TIME_PER_SAMPLE = 0.083
powers = []

pylab.hold(False)

tlock = threading.Lock()

def sigint_handler(signal, frame):
	dataLog.stop = True
	dataRead.stop = True
	sys.exit(0)

class DataPlotter:
	def __init__(self):
		self.data_x = []
		self.data_y = []
		self.data_i = []
		self.data_v = []

		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.set_default_size(550, 700)
		self.window.connect("delete_event", self.destroy)
		self.window.connect("destroy", self.destroy)

		self.vbox = gtk.VBox(False, 0)
		self.window.add(self.vbox)

		self.plotfig_i = Figure(figsize=(100, 100), dpi=75)
		self.plotfig_v = Figure(figsize=(100, 100), dpi=75)
		self.plotax_i = self.plotfig_i.add_subplot(111)
		self.plotax_v = self.plotfig_v.add_subplot(111)
		self.plotlines_i = self.plotax_i.plot(self.data_x, self.data_i, '.')
		self.plotlines_v = self.plotax_v.plot(self.data_x, self.data_v, '.')

		self.plotax_i.set_ylim(-15, 15)
		self.plotax_v.set_ylim(0, 178)

		self.plotcanvas_i = FigureCanvasGTK(self.plotfig_i)
		self.plotcanvas_v = FigureCanvasGTK(self.plotfig_v)
		self.plotcanvas_i.show()
		self.plotcanvas_v.show()

		self.vbox.pack_start(self.plotcanvas_i, True, True, 0)
		self.vbox.pack_end(self.plotcanvas_v, True, True, 0)
		self.vbox.show()


	def destroy(self, widget, data=None):
		gtk.main_quit()
		sigint_handler(0, 0)

	def data_adjust(self):
		x = -1
		y = -1
		self.data_i = []
		self.data_v = []

		self.data_y.pop(0)
		self.data_x.pop(0)

		for i in range(len(self.data_y)):
			if (i % 2 == 0):
				self.data_y[i] *= (170000/4300.)/1000
				if (y != -1):
					self.data_v.append((y + self.data_y[i]) / 2)
				else:
					self.data_v.append(self.data_y[i])
				self.data_v.append(self.data_y[i])
				y = self.data_y[i]
			else:
				self.data_y[i] -= 2500
				self.data_y[i] /= 100
				if (x != -1):
					self.data_i.append((x + self.data_y[i]) / 2)
				else:
					self.data_i.append(self.data_y[i])
				self.data_i.append(self.data_y[i])
				x = self.data_y[i]


		power = 0

		# Perform a numerical integration on this power
		for i in range(len(self.data_i)):
			power += abs(self.data_i[i]) * self.data_v[i]
		# Divide by the time length for the average power
		power /= (len(self.data_y))
		# Divide by two since we took the absolute value of
		# both I and V
		#power /= 2.

		# Subtract our "idle" power value
		#power -= 18.30
		#if (power < 0):
		#	power = 0

		# Push this power to our list
		powers.insert(0, power)
		# Pop off the first if we've reached 6 powers
		if (len(powers) == 6):
			powers.pop()

		# Print out current list of powers
		print "Power:",
		avgpower = 0
		for i in range(len(powers)):
			if (i == 0):
				print "[%f]" % powers[i],
			else:
				print "%f" % powers[i],
			avgpower += powers[i]
		print "watts"

		# Calculate and print the average power
		avgpower /= (len(powers) + 0.0)
		print "Average Power: %f" % avgpower, "watts"
		print "Latest Power Reading: %f" % power, "watts\n\n"

	def replot(self):
		if (dataLog.new_data > 0):
			self.data_x = dataLog.back_axis_time[:]
			self.data_y = dataLog.back_axis_voltage[:]
			self.data_adjust()
			self.plotlines_i[0].set_xdata(self.data_x)
			self.plotlines_v[0].set_xdata(self.data_x)
			self.plotlines_i[0].set_ydata(self.data_i)
			self.plotlines_v[0].set_ydata(self.data_v)
			self.plotlines_i[0].set_color('r')
			self.plotlines_v[0].set_color('r')

			self.plotax_i.set_xlim(self.data_x[0], self.data_x[-1])
			self.plotax_v.set_xlim(self.data_x[0], self.data_x[-1])
			dataLog.new_data = 0

		self.plotcanvas_i.draw_idle();
		self.plotcanvas_v.draw_idle();
		return True

	def main(self):
		self.window.show()
		gobject.idle_add(self.replot)
		gtk.main()

class DataLogger(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)

		self.axis_time = []
		self.axis_voltage = []

		self.back_axis_time = []
		self.back_axis_voltage = []

		self.new_data = 0

		self.stop = False


	def parse_Samples(self):
		timestamp_str = ''
		timestamp = 0
		timeindex = 0

		number_str = ''
		data = 0
		voltage = 0

		state = -1
		for rawData in self.dataCopy:
			if (rawData == 'T'):
				state = 1
				self.axis_time = []
				self.axis_voltage = []
				continue
			elif (rawData == 'S' and state != -1):
				state = 2
				continue
			elif ((rawData == 'X' or rawData == 'Y') and state != -1):
				self.back_axis_time = self.axis_time[:]
				self.back_axis_voltage = self.axis_voltage[:]
				self.new_data = 1
				state = 0
				break

			if (state == 1):
				timestamp_str += rawData
				if (len(timestamp_str) == 8):
					timestamp = int(timestamp_str, 16)
					timeindex = timestamp
					timestamp_str = ''
					state = 0

			if (state == 2):
				if (rawData == ',' or len(number_str) == 3):
					if (len(number_str) != 3):
						number_str = ''
						continue
					timeindex += TIME_PER_SAMPLE
					try:
						data = int(number_str, 16)
					except ValueError:
						#print "Error with this number string: %s" % number_str
						state = -1
						break
					voltage = 5000*(data/1024.)

					self.axis_time.append(timeindex)
					self.axis_voltage.append(voltage)
					#print "%f %f" % (timeindex, voltage)
					number_str = ''
				else:
					number_str += rawData

	def run(self):
		while not self.stop:
			if (dataRead.new_data == 1):
				self.dataCopy = copy.copy(dataRead.dataCopy)
				self.parse_Samples()
				dataRead.new_data = 0

class DataReader(threading.Thread):
	def __init__(self, portPath):
		threading.Thread.__init__(self)
		self.dataBuffer = ''
		self.dataCopy = ''
		self.new_data = 0
		self.stop = False

	# Open the serial port
		try:
			self.sp = serial.Serial(portPath, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1);
		except serial.SerialException as (strError):
			print "Error opening serial port!: ", strError,
			sys.exit(1)


	def run(self):
		rawData = ''
		while not self.stop:
			# Read raw data from the serial port
			rawData = self.sp.read(1)
			# If the read didn't time out, send it over for processing
			if (len(rawData) > 0):
				self.dataBuffer += rawData
				if (rawData == 'X'):
					self.dataCopy = copy.copy(self.dataBuffer)
					self.dataBuffer = ''
					self.new_data = 1

if __name__ == '__main__':
	signal.signal(signal.SIGINT, sigint_handler)
	dataRead = DataReader(sys.argv[1])
	dataLog = DataLogger()
	dataLog.start()
	dataRead.start()

	dataPlot = DataPlotter()
	dataPlot.main()
