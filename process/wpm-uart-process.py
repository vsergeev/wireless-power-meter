import sys
import time
import signal
import struct
import serial
import threading

################################################################################
################################################################################

TIME_PER_SAMPLE = 0.083

################################################################################
################################################################################

# Timestamp ascii hex characters
timestamp_str = ''
# Timestamp converted to a number
timestamp = 0

# Sample data ascii hex characters
number_str = ''
# Sample data converted to a number
data = 0
# Adjusted sample data to voltage
voltage = 0

# Checksum ascii hex characters
checksum_str = ''
# Checksum data converted to a number
sample_checksum = -1
# Locally computed checksum on the data
local_checksum = 0

# Zigbee permanent addresses list
paList = []
# Map of data bytes corresponding to zigbee permanent address list
dataMapList = []
# Fully assembled sample data buffer list
sampleDataList = []

# Index of the last current meter processed
last_processed_index = -1

# Formatted sample data
print_buffer = ''

# Yet to be processed serial port data
unprocessedData = ''

# A simple sigint handler to stop the reading thread
def sigint_handler(signal, frame):
	inputFile.close()
	outputFile.close()
	sys.exit(0)

# Perform a CRC16 on 8-bit data blocks with a 16-bit seed
def crc16_bits(data, seed):
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

# Parses the actual assembled sample data
def parse_Samples(index):
	global timestamp_str, timestamp, timeindex, checksum_str, sample_checksum, number_str, data, voltage, last_processed_index, print_buffer

	# Ensure that we have both packet start and packet ends
	if (sampleDataList[index].find('T') < 0 or sampleDataList[index].find('Z') < 0):
		sampleDataList[index] = ''
		return -1

	local_checksum = 0
	state = -1
	for rawData in sampleDataList[index]:
		if (rawData == 'T'):
			state = 1
			print_buffer = ''
			continue
		elif (rawData == 'S' and state != -1):
			state = 2
			continue
		elif ((rawData == 'X' or rawData == 'Y') and state != -1):
			state = 3
			continue
		elif ((rawData == 'Z') and state != -1):
			# Only print the buffer of samples if our local checksum
			# matches
			if (local_checksum == sample_checksum):
				outputFile.write(print_buffer)
				outputFile.flush()
				print "New samples from %s!" % paList[index]
				# Set our last processed index to this index
				last_processed_index = index
			break

		# State: Timestamp Data
		if (state == 1):
			# Add the timestamp ascii hex character to our string
			timestamp_str += rawData
			# Convert the string once its reached its max length
			if (len(timestamp_str) == 8):
				try:
					timestamp = int(timestamp_str, 16)
				except ValueError:
					return -1
				# Calculate our local checksum based on all
				# of the bytes of the timestamp number
				local_checksum = crc16_bits((timestamp >> 24) & 0xFF, local_checksum)
				local_checksum = crc16_bits((timestamp >> 16) & 0xFF, local_checksum)
				local_checksum = crc16_bits((timestamp >> 8) & 0xFF, local_checksum)
				local_checksum = crc16_bits(timestamp & 0xFF, local_checksum)
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
				try:
					data = int(number_str, 16)
				except ValueError:
					return -1
				# Run the data through our local checksum
				local_checksum = crc16_bits((data >> 8) & 0xFF, local_checksum)
				local_checksum = crc16_bits(data & 0xFF, local_checksum)
				# Scale the data to an actual voltage
				voltage = 5.0*(data/1024.)
				# Add this sample to our print buffer
				print_buffer += "%f %s %f\n" % (timestamp, paList[index], voltage)
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
				try:
					sample_checksum = int(checksum_str, 16)
				except ValueError:
					return -1
				# Reset the checksum string
				checksum_str = ''
				state = 0

	sampleDataList[index] = ''
	return 0

# Parses API frame data and sequences the sample frame data
def parse_Frame_Data(data, dataLen):
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
		index = paList.index(permanentAddress)
	except ValueError:
		# Otherwise add the device to our list
		paList.append(permanentAddress)
		# Create a new data map for this device
		dataMapList.append({})
		# Create a new sample data buffer in our list
		sampleDataList.append('')
		index = len(paList)-1

	# Extract the sample data
	sampleData = data[13:(13+dataLen)]

	print "Sample data from %s with frameID %d" % (permanentAddress, frameID)

	# If we already have this frame in our data map, clear our data map
	# before adding the frame data
	if (dataMapList[index].has_key(frameID) == True):
		dataMapList[index].clear()

	# Add the sample data to our data map
	dataMapList[index][frameID] = sampleData[:]

	# Check if this packet is the end of the sample data
	if (sampleData.find('Z') >= 0):
		# Sort all of the keys in our data map
		keys = dataMapList[index].keys()
		keys.sort()
		# Clear our sample buffer
		sampleDataList[index] = ''
		# Make sure the 0th key is the 0th frame ID
		if (keys[0] == 0):
			# Check that all other frame IDs follow in order, and
			# assemble the sample buffer
			for i in range(len(keys)):
				# If they're out of order, clear the data map
				if (keys[i] != i):
					dataMapList[index].clear()
					return -1
				# Assemble the sample buffer
				sampleDataList[index] += dataMapList[index][keys[i]]

			# Clear the data map now that we're done with it
			dataMapList[index].clear()
			# The 0th key is the 0th frame ID and all other frame
			# IDs follow in order, time to parse the sample data
			parse_Samples(index)
		else:
			# If the 0th key is not the 0th frame ID
			dataMapList[index].clear()
			return -1

	return 0

# Parses API frames for the frame data
def parse_API_Frame(data):
	global unprocessedData
	retVal = 0

	dataLen = len(data)

	# If we have unprocessed data from our last parsing attempt,
	# insert it before out current data and adjust our data length
	if (len(unprocessedData) > 0):
		data = unprocessedData + data
		dataLen += len(unprocessedData)
		unprocessedData = ''

	# Minimum length of frame: start, length MSB, length LSB, checksum
	if dataLen < 4:
		return -1

	# Unpack the frame into an array of databytes
	dataBytes = struct.unpack(str(dataLen) + "B", data)

	for i in range(dataLen):
		# Check for the start of an API frame
		if dataBytes[i] == 0x7E:
			# Check that the next two length bytes and at least
			# the checksum byte exist, otherwise skip this frame
			# (but save it for later in unprocessedData)
			if dataLen < i+3:
				unprocessedData += data[i:]
				break

			# Pull out the API frame length from the next two bytes
			frameLen = dataBytes[i+1]<<8
			frameLen += dataBytes[i+2]

			# Check that the frame actually contains this specified
			# frame length, otherwise skip the frame
			# (but save it for later in unprocessedData)
			if dataLen < (i+3+frameLen+1):
				unprocessedData += data[i:]
				break

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
			retVal = parse_Frame_Data(frameData, frameLen)
	return retVal

def process_loop(dataRead):
	dataCopy = ''
	timeout = 0

	while (True):
		data = inputFile.read(255)
		if (len(data) > 0):
			parse_API_Frame(data)
		else:
			break


# Check for minimum arguments
if (len(sys.argv) < 3):
	print "Usage: %s <input file> <output file>" % sys.argv[0]
	sys.exit(1)

# Open our data file
try:
	inputFile = open(sys.argv[1], "r")
	outputFile = open(sys.argv[2], "w")
except IOError as (strError):
	print "Error opening file: %s" % strError

# Set up our signal handler
signal.signal(signal.SIGINT, sigint_handler)

# Process all of the data in the input file
process_loop(inputFile)

# Close our input and output files
inputFile.close()
outputFile.close()
