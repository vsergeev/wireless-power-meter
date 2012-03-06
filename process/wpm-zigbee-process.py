import random
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
powers.append([])

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
		self.data_x.append([0])
		self.data_y.append([0])
		self.data_i.append([0])
		self.data_v.append([0])
		self.colors = ['r', 'b', 'c', 'm', 'g', 'y']

		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.set_default_size(550, 700)
		self.window.connect("delete_event", self.destroy)
		self.window.connect("destroy", self.destroy)

		self.vbox = []
		self.vbox.append(gtk.VBox(False, 0))

		self.hbox = gtk.HBox(False, 0)
		self.hbox.pack_start(self.vbox[0], True, True, 0)
		self.window.add(self.hbox)

		self.plotfig_i = Figure(figsize=(100, 100), dpi=75)
		self.plotfig_v = Figure(figsize=(100, 100), dpi=75)
		self.plotax_i = []
		self.plotax_v = []
		self.plotax_i.append(self.plotfig_i.add_subplot(111))
		self.plotax_v.append(self.plotfig_v.add_subplot(111))
		self.plotlines_i = []
		self.plotlines_v = []
		self.plotlines_i.append(self.plotax_i[0].plot(self.data_x[0], self.data_i[0], '.'))
		self.plotlines_v.append(self.plotax_v[0].plot(self.data_x[0], self.data_v[0], '.'))

		self.plotax_i[0].set_ylim(-10, 10)
		self.plotax_v[0].set_ylim(0, 178)

		self.plotcanvas_i = []
		self.plotcanvas_v = []
		self.plotcanvas_i.append(FigureCanvasGTK(self.plotfig_i))
		self.plotcanvas_v.append(FigureCanvasGTK(self.plotfig_v))
		self.plotcanvas_i[0].show()
		self.plotcanvas_v[0].show()

		self.vbox[0].pack_start(self.plotcanvas_i[0], True, True, 0)
		self.vbox[0].pack_end(self.plotcanvas_v[0], True, True, 0)
		self.vbox[0].show()

		self.hbox.show()

	def destroy(self, widget, data=None):
		gtk.main_quit()
		sigint_handler(0, 0)

	def data_adjust(self, index):
#		if (toggle == 1):
#			if (dataType == 1):
#				for i in range(len(self.data_i)):
#					self.data_i[i] -= 2500.
#					self.data_i[i] /= 100.
#			elif (dataType == 2):
#				for i in range(len(self.data_i)):
#					self.data_v[i] *= (170000/4250.)/1000
#		else:
		x = -1
		y = -1
		self.data_i[index] = []
		self.data_v[index] = []

		for i in range(len(self.data_y[index])):
			if (i % 2 == 0):
				self.data_y[index][i] -= 2500
				self.data_y[index][i] /= 100
				if (x != -1):
					self.data_i[index].append((x + self.data_y[index][i]) / 2)
				else:
					self.data_i[index].append(self.data_y[index][i])
				self.data_i[index].append(self.data_y[index][i])
				x = self.data_y[index][i]
			else:
				self.data_y[index][i] *= (170000/4300.)/1000
				if (y != -1):
					self.data_v[index].append((y + self.data_y[index][i]) / 2)
				else:
					self.data_v[index].append(self.data_y[index][i])
				self.data_v[index].append(self.data_y[index][i])
				y = self.data_y[index][i]

		power = 0

		print "\n[%d] Power Information for %s" % (index, dataLog.paList[index])
		#print "index: %d len x: %d len y: %d" % (index, len(self.data_i[index]), len(self.data_v[index]))

		# Perform a numerical integration on this power
		for i in range(len(self.data_i[index])):
			power += abs(self.data_i[index][i]) * self.data_v[index][i]
		# Divide by the time length for the average power
		power /= (len(self.data_y[index]))
		# Divide by two since we took the absolute value of
		# both I and V
		power /= 2.

		# Subtract our "idle" power value
		power -= 18.30
		if (power < 0):
			power = 0


		# Push this power to our list
		powers[index].insert(0, power)
		# Pop off the first if we've reached 6 powers
		if (len(powers[index]) == 6):
			powers[index].pop()

		# Print out current list of powers
		print "[%d] Power:" % index,
		avgpower = 0
		for i in range(len(powers[index])):
			if (i == 0):
				print "[%f]" % powers[index][i],
			else:
				print "%f" % powers[index][i],
			avgpower += powers[index][i]
		print "watts"

		# Calculate and print the average power
		avgpower /= (len(powers[index]) + 0.0)
		print "[%d] Average Power:" % index, avgpower, "watts"
		print "[%d] Latest Power Reading:" % index, power, "watts\n\n"

	def replot(self):
		if (dataLog.new_data > 0):
			cindex = dataLog.new_data-1
					# If this is a new meter, add it to our data / plotline arrays
			while (dataLog.new_data > len(self.data_x)):
				newMemberID = len(self.data_x)
				#print "new member!"
				self.data_x.append([0])
				self.data_y.append([0])
				self.data_i.append([0])
				self.data_v.append([0])
				self.vbox.append(gtk.VBox(False, 0))
				pi = Figure(figsize=(100, 100), dpi=75)
				pv = Figure(figsize=(100, 100), dpi=75)
				self.plotax_i.append(pi.add_subplot(111))
				self.plotax_v.append(pv.add_subplot(111))
				self.plotlines_i.append(self.plotax_i[newMemberID].plot(self.data_x[newMemberID], self.data_i[newMemberID], '.'))
				self.plotlines_v.append(self.plotax_v[newMemberID].plot(self.data_x[newMemberID], self.data_v[newMemberID], '.'))
				self.plotax_i[newMemberID].set_ylim(-10, 10)
				self.plotax_v[newMemberID].set_ylim(0, 178)

				self.plotcanvas_i.append(FigureCanvasGTK(pi))
				self.plotcanvas_v.append(FigureCanvasGTK(pv))
				self.plotcanvas_i[newMemberID].show()
				self.plotcanvas_v[newMemberID].show()

				self.vbox[newMemberID].pack_start(self.plotcanvas_i[newMemberID], True, True, 0)
				self.vbox[newMemberID].pack_end(self.plotcanvas_v[newMemberID], True, True, 0)
				self.vbox[newMemberID].show()
				self.hbox.pack_end(self.vbox[newMemberID], True, True, 0)
				self.hbox.show()

				powers.append([])

			self.data_x[cindex] = dataLog.back_axis_time[cindex][:]
			self.data_y[cindex] = dataLog.back_axis_voltage[cindex][:]
			if (len(self.data_x[cindex]) % 2 != 0 or len(self.data_y[cindex]) % 2 != 0):
				dataLog.new_data = 0
				return True


			#print "index: %d len x: %d len y: %d" % (cindex, len(self.data_x[cindex]), len(self.data_y[cindex]))
			self.data_adjust(cindex)
			for i in range(len(self.plotlines_i)):
				self.plotlines_i[i][0].set_xdata(self.data_x[i])
				self.plotlines_v[i][0].set_xdata(self.data_x[i])
				self.plotlines_i[i][0].set_ydata(self.data_i[i])
				self.plotlines_v[i][0].set_ydata(self.data_v[i])
				self.plotlines_i[i][0].set_color(self.colors[i])
				self.plotlines_v[i][0].set_color(self.colors[i])

			self.plotax_i[cindex].set_xlim(self.data_x[cindex][0], self.data_x[cindex][-1])
			self.plotax_v[cindex].set_xlim(self.data_x[cindex][0], self.data_x[cindex][-1])
			dataLog.new_data = 0

		for i in range(len(self.plotcanvas_i)):
			self.plotcanvas_i[i].draw_idle();
			self.plotcanvas_v[i].draw_idle();
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


		# Zigbee permanent addresses list
		self.paList = []
		# Map of data bytes corresponding to zigbee permanent address list
		self.dataMapList = []
		# Fully assembled sample data buffer list
		self.sampleDataList = []
		# Time index list
		self.tiList = []

		# Index of the last current meter processed
		self.last_processed_index = -1

		# Yet to be processed serial port data
		self.unprocessedData = ''

		self.timeout = 0

	# Perform a CRC16 on 8-bit data blocks with a 16-bit seed
	def crc16_bits(self, data, seed):
		feedback = 0

		# Keep our variables bound to 8/16 bits
		data = data & 0xFF
		seed = seed & 0xFFFF

		# CRC16 Algorithm
		for i in range(8):
			feedback = ((data>>7) ^ (seed>>15)) & 0x1
			if (feedback == 0):
				seed <<= 1
				seed = seed & 0xFFFF
			else:
				seed ^= (0x10 | 0x800)
				seed <<= 1
				seed |= 0x01
				seed = seed & 0xFFFF
			data <<= 1
			data = data & 0xFF

		return seed

	def parse_Samples(self, index):
		timestamp_str = ''
		timestamp = 0

		checksum_str = ''
		sample_checksum = -1
		local_checksum = 0

		number_str = ''
		data = 0
		voltage = 0

		print_buffer = ''

		# Ensure that we have both packet start and packet ends
		if (self.sampleDataList[index].find('T') < 0 or self.sampleDataList[index].find('Z') < 0):
			return -1

		state = -1
		for rawData in self.sampleDataList[index]:
			if (rawData == 'T'):
				state = 1
				self.axis_time[index] = []
				self.axis_voltage[index] = []
				continue
			elif (rawData == 'S' and state != -1):
				state = 2
				continue
			elif ((rawData == 'X' or rawData == 'Y') and state != -1):
				state = 3
				continue
			elif ((rawData == 'Z') and state != -1):
				# Make sure our time and data axis match up
				if (len(self.axis_time[index]) != len(self.axis_voltage[index])):
					break

				# If we already have new data we need to process
				# and we just processed this meter, skip it
				#if (self.new_data != 0):
				#	if (index == self.last_processed_index):
				#		print "skipped"
				#		break
				#	else:
				#		print "not skipped"
				#		self.last_processed_index = -1
				#		break

				# Only offer new data to plot if the checksum matches
				if (local_checksum == sample_checksum):
					self.back_axis_time[index] = self.axis_time[index][:]
					self.back_axis_voltage[index] = self.axis_voltage[index][:]
					self.new_data = index+1
					# Set our last processed index to this index
					self.last_processed_index = index
					# Wait until this data has been plotted
					while (self.new_data != 0):
						pass
				else:
					self.last_processed_index = index
					break

				# Clear all acquire data
				self.unprocessedData = ''
				for i in range(len(self.paList)):
					self.dataMapList[i].clear()

				break

			# State: Timestamp Data
			if (state == 1):
				# Add the timestamp ascii hex character to our string
				timestamp_str += rawData
				# Convert the string once its reached its max length
				if (len(timestamp_str) == 8):
					timestamp = int(timestamp_str, 16)
					# Make sure this is a newer sample
					if (self.tiList[index] != -1 and self.tiList[index] > timestamp):
						# Clear all acquire data
						self.unprocessedData = ''
						for i in range(len(self.paList)):
							self.dataMapList[i].clear()
						break
					self.tiList[index] = timestamp
					# Calculate our local checksum based on all
					# of the bytes of the timestamp number
					local_checksum = self.crc16_bits((timestamp >> 24) & 0xFF, local_checksum)
					local_checksum = self.crc16_bits((timestamp >> 16) & 0xFF, local_checksum)
					local_checksum = self.crc16_bits((timestamp >> 8) & 0xFF, local_checksum)
					local_checksum = self.crc16_bits(timestamp & 0xFF, local_checksum)
					# Reset the timestamp string
					timestamp_str = ''
					state = 0

			# State: Sample Data
			if (state == 2):
				# If our number string has reached max length or we
				# encounter a comma
				if (rawData == ',' or len(number_str) == 3):
					# If we're not at the necessary length, reset
					# the number string
					if (len(number_str) != 3):
						number_str = ''
						continue

					# Convert the number string to its actual data
					data = int(number_str, 16)
					# Run the data through our local checksum
					local_checksum = self.crc16_bits((data >> 8) & 0xFF, local_checksum)
					local_checksum = self.crc16_bits(data & 0xFF, local_checksum)
					# Scale the data to an actual voltage
					voltage = 5000.*(data/1024.)
					# Add this sample to our time and voltage data lists
					self.axis_time[index].append(timestamp)
					self.axis_voltage[index].append(voltage)
					# Increment our timestamp to align with our
					# next sample
					timestamp += TIME_PER_SAMPLE
					# Reset the number string
					number_str = ''
				else:
					# Append this ascii hex data to our number
					# string
					number_str += rawData

			# State: Checksum Data
			if (state == 3):
				# Append this ascii hex data to our checksum string
				checksum_str += rawData
				# Make sure we haven't gone over the checksum string
				# length
				if (len(checksum_str) > 4):
					# If so, reset the checksum_str and state
					checksum_str = ''
					state = 0
				# If we've reached necessary length of our checksum
				# string
				elif (len(checksum_str) == 4):
					# Convert the checksum ascii hex to a number
					sample_checksum = int(checksum_str, 16)
					# Reset the checksum string
					checksum_str = ''
					state = 0

		self.sampleDataList[index] = ''
		return 0

	def parse_Frame_Data(self, data, dataLen):
		retVal = 0

		# Unpack the frame data into an array of databytes
		dataBytes = struct.unpack(str(dataLen) + "B", data)

		# Check that the frame data type is a Zigbee Receive Packet
		if dataBytes[0] != 0x90:
			return -1

		# Check that the frame data contains the sample information we need
		if dataLen < 13:
			return -1

		# Pull out the permanent and network addresses
		permanentAddress = ""
		for i in range(2, 10):
			permanentAddress += "%02X" % dataBytes[i]

		# (we don't actually use the network address for anything)
		#networkAddress = "%02X%02X" % (dataBytes[10], dataBytes[11])

		# Subtract the length of frame data type, frame id, permanent address,
		# network address, and receive options byes -- essentially the header
		dataLen -= (2+8+2+1)

		# Make sure we have actual data left over
		if (dataLen <= 0):
			return -1

		# Extract the Frame ID
		frameID = dataBytes[12]

		# Check if we have this device in our permanent address list
		try:
			index = self.paList.index(permanentAddress)
		except ValueError:
			# Otherwise add the device to our list
			self.paList.append(permanentAddress)
			# Create a new data map for this device
			self.dataMapList.append({})
			# Create a new sample data buffer in our list
			self.sampleDataList.append('')
			self.tiList.append(-1)
			index = len(self.paList)-1
			self.axis_voltage.append([])
			self.axis_time.append([])
			self.back_axis_voltage.append([])
			self.back_axis_time.append([])

		# Don't collect this data if we just processed this meter
		if (len(self.paList) > 1 and self.last_processed_index >= 0 and self.last_processed_index == index):
			self.unprocessedData = ''
			#for i in range(len(self.paList)):
			#	self.dataMapList[i].clear()
			#self.last_processed_index = -1
			if (self.timeout == 0):
				self.timeout_index = index
			self.timeout += 1
			if (self.timeout >= 50):
				self.last_processed_index = -1
			return -1
		else:
			self.timeout_index = -1
			self.timeout = 0

		# Extract the sample data
		sampleData = data[13:(13+dataLen)]

		# If we already have this frame in our data map, clear our data map
		# before adding the frame data
		if (self.dataMapList[index].has_key(frameID) == True):
			self.dataMapList[index].clear()
			# Only add the frame if we're restarting at 0
		#	if (self.last_processed_index == -1 and frameID != 0):
		#		return -1

		# Add the sample data to our data map
		self.dataMapList[index][frameID] = sampleData[:]

		# Check if this packet is the end of the sample data
		if (sampleData.find('Z') >= 0):
			# Sort all of the keys in our data map
			keys = self.dataMapList[index].keys()
			keys.sort()
			# Clear our sample buffer
			self.sampleDataList[index] = ''
			# Make sure the 0th key is the 0th frame ID
			if (keys[0] == 0):
				# Check that all other frame IDs follow in order, and
				# assemble the sample buffer
				for i in range(len(keys)):
					# If they're out of order, clear the data map
					if (keys[i] != i):
						self.dataMapList[index].clear()
						return -1
					# Assemble the sample buffer
					self.sampleDataList[index] += self.dataMapList[index][keys[i]]

				# Clear the data map now that we're done with it
				self.dataMapList[index].clear()
				# The 0th key is the 0th frame ID and all other frame
				# IDs follow in order, time to parse the sample data
				retVal = self.parse_Samples(index)
			else:
				# If the 0th key is not the 0th frame ID
				self.dataMapList[index].clear()
				return -1

		return retVal


	def parse_API_Frame(self, data):
		dataLen = len(data)

		# Minimum length of frame: start, length MSB, length LSB, checksum
		if dataLen < 4:
			return -1

		# If we have unprocessed data from our last parsing attempt,
		# insert it before out current data and adjust our data length
		if (len(self.unprocessedData) > 0):
			data = self.unprocessedData + data
			dataLen += len(self.unprocessedData)
			self.unprocessedData = ''

		# Unpack the frame into an array of databytes
		dataBytes = struct.unpack(str(dataLen) + "B", data)

		for i in range(dataLen):
			# Check for the start of an API frame
			if dataBytes[i] == 0x7E:
				# Check that the next two length bytes and at least
				# the checksum byte exist, otherwise skip this frame
				# (but save it for later in unprocessedData)
				if dataLen < i+3:
					self.unprocessedData += data[i:]
					continue

				# Pull out the API frame length from the next two bytes
				frameLen = dataBytes[i+1]<<8
				frameLen += dataBytes[i+2]

				# Check that the frame actually contains this specified
				# frame length, otherwise skip the frame
				# (but save it for later in unprocessedData)
				if dataLen < (i+3+frameLen+1):
					self.unprocessedData += data[i:]
					continue

				# Calculate the checksum of the frame
				checksum = 0
				for j in range(i+3, i+3+frameLen+1):
					checksum += dataBytes[j]
					checksum = (checksum & 0xFF)

				# Check for an invalid frame
				if (checksum != 0xFF):
					continue

				# Extract the actual frame data
				frameData = data[i+3 : i+3+frameLen]

				# Pass it along to our frame data parsing function
				self.parse_Frame_Data(frameData, frameLen)
		return 0


	def run(self):
		while not self.stop:
			if (dataRead.new_data == 1):
				self.dataCopy = copy.copy(dataRead.dataCopy)
				self.parse_API_Frame(self.dataCopy)
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
			rawData = self.sp.read(50)
			sys.stdout.write(".")
			sys.stdout.flush()
			#print "got data len %d" % len(rawData)
			# If the read didn't time out, send it over for processing
			if (len(rawData) > 0):
				self.dataBuffer += rawData
				if (len(self.dataBuffer) >= 100):
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
