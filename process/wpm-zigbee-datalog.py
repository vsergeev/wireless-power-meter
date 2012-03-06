import sys
import time
import struct
import serial
import signal

################################################################################
################################################################################

TIME_PER_SAMPLE = 0.083

################################################################################
################################################################################

# A simple sigint handler to stop the reading
def sigint_handler(signal, frame):
	readStop = True
	dataFile.close()
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

################################################################################
################################################################################

# Check for minimum arguments
if (len(sys.argv) < 3):
	print "Usage: %s <serial port> <output file>" % sys.argv[0]
	sys.exit(1)

# Open our data file
try:
	dataFile = open(sys.argv[2], "w")
except IOError as (strError):
	print "Error opening file: %s" % strError

# Open the serial port
try:
	sp = serial.Serial(sys.argv[1], baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1);
except serial.SerialException as (strError):
	print "Error opening serial port!: ", strError
	sys.exit(1)

# Set up our signal handler
signal.signal(signal.SIGINT, sigint_handler)

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

# Formatted sample data
print_buffer = ''

# A signal set by sigint to stop reading
readStop = False

state = -1

while not readStop:
	# Read raw data from the serial port
	rawData = sp.read(1)
	# If the read didn't time out, send it over for processing
	if (len(rawData) > 0):
		if (rawData == 'T'):
			state = 1
			timestamp_str = ''
			number_str = ''
			# Reset the checksum data and the print buffer
			sample_checksum = -1
			local_checksum = 0
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
				dataFile.write(print_buffer)

			# Reset the state
			state = -1
			continue

		# State: Timestamp Data
		if (state == 1):
			# Add the timestamp ascii hex character to our string
			timestamp_str += rawData
			# Convert the string once its reached its max length
			if (len(timestamp_str) == 8):
				timestamp = int(timestamp_str, 16)
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
					state = 0
					continue
				# Run the data through our local checksum
				local_checksum = crc16_bits((data >> 8) & 0xFF, local_checksum)
				local_checksum = crc16_bits(data & 0xFF, local_checksum)
				# Scale the data to an actual voltage
				voltage = 5.0*(data/1024.)
				# Add this sample to our print buffer
				print_buffer += "%f %f\n" % (timestamp, voltage)
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

# Close the serial port and the data file
sp.close()

