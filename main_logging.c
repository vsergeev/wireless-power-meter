
#include "uart.h"
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>
#include <stdint.h>

#define XBEE_ACK

/* Hardware constants: LED pins, ADC input channels for V and I */
#define XBEE_DETECT		(1<<0)
#define LED_1			(1<<1)
#define LED_2			(1<<2)
#define ADC_CHANNEL_CURRENT	0
#define ADC_CHANNEL_VOLTAGE	1

/* Size of the ADC buffer, tuned to be 16.8 milliseconds long, or one
 * wavelength of a 60Hz signal */
#define ADC_SAMPLE_BUFFER_SIZE		404+1
uint16_t ADC_SAMPLE_BUFFER_SIZE_V;
/* The time between ADC samples (determined by the ADC clock rate setting
 * in ADC_init() */
#define ADC_SAMPLE_TIME		83

/* Number of ADC samples to test before concluding we are at the right part
 * of the wave to start logging */
#define ADC_TEST_BUFFER_SIZE	10

/* Zero-crossing points for the voltage and current waves from which the ADC
 * will start sampling */
#define ADC_DATA_START_VOLTAGE	0
#define ADC_DATA_START_CURRENT	512

/* Timestamp of this ADC buffer */
volatile uint16_t adc_msHigh = 0;
volatile uint16_t adc_msLow = 0;

/* The ADC sample buffer */
volatile uint16_t adcSampleBuffer[ADC_SAMPLE_BUFFER_SIZE];
volatile uint16_t adcSampleIndex = 0;

/* Signal to the main loop that we have new data to read */
volatile uint8_t adcDataReady = 0;

/* System millisecond timer built from the ADC interrupt handler */
volatile uint16_t msHigh = 0;
volatile uint16_t msLow = 0;
volatile uint16_t usCount = 0;

ISR(ADC_vect) {
	/* Count elapsed [83] microseconds */
	usCount++;

	/* Once 1000*83 microseconds have passed, 83 milliseconds have
	 * passed. */
	if (usCount == 1000) {
		/* Check for overflow from 1024 milliseconds, if so, increment
		 * msHigh */
		if ((msLow + ADC_SAMPLE_TIME) < msLow)
			msHigh++;
		/* Increment our low milliseconds */
		msLow += ADC_SAMPLE_TIME;
		usCount = 0;
	}

	if (adcDataReady == 0) {
		if (adcSampleIndex == 0) {
			/* Otherwise, beginning of normal sampling */
			/* Make sure our microsecond counter restarted */
			if (usCount != 0)
				return;

			adc_msHigh = msHigh;
			adc_msLow = msLow;
		}

		/* Read the sample into the buffer */
		adcSampleBuffer[adcSampleIndex] = ADCL;
		adcSampleBuffer[adcSampleIndex] |= (ADCH << 8);
		adcSampleIndex++;

		/* Toggle between current and voltage channels */
		if (ADMUX & (1<<0)) {
			ADMUX &= ~(1<<0);
		} else {
			ADMUX |= (1<<0);
		}

		/* Check if we've reached the end of the buffer */
		if (adcSampleIndex == ADC_SAMPLE_BUFFER_SIZE_V) {
			adcDataReady = 1;
			adcSampleIndex = 0;
			ADMUX |= (1<<0);
			PORTB &= ~LED_1;
		}

		/* Toggle the sampling LED */
		if (PORTB & LED_1)
			PORTB &= ~LED_1;
		else
			PORTB |= LED_1;
	}
}

void ADC_init(void) {
	/* Disable global interrupts temporarily */
	cli();

	/* Make our ADC channels inputs */
	DDRC &= ~((1<<1)|(1<<0));

	/* Configure ADC Multiplexer
	 * [7:6] REFS1:0 = 01 for AVcc voltage reference
	 * [3:0] MUX3:0 = 0000 for ADC0, 0001 for ADC1 */
	ADMUX = ((1<<6) | (1<<0));

	/* Configure Digital Input Disable Register 0
	 * [5:0] = ADC5D - ADC0D = 11111 to disable digital input buffer
	 *         for ADC0-ADC5 to reduce power consumption. */
	DIDR0 = 0x1F;

	/* Configure ADC Control and Status Register B
	 * [2:0] ADTS2:0 = 100 for Timer/Counter0 Overflow
	 * [2:0] ADTS2:0 = 000 for Free Running mode */
	ADCSRB = 0;

	/* Configure ADC Control and Status Register A
	 * [7] ADEN = 1 to enable ADC
	 * [6] ADSC = 1 to start the conversion
	 * [5] ADATE = 1 to enable trigger of ADC
	 * [3] ADIE = 1 to enable ADC interrupt
	 * [2:0] ADPS2:0 = 111 for 128 prescaling = 156.25kHz */
	ADCSRA = ((1<<7) | (1<<6) | (1<<5) | (1<<3) | (1<<2) | (1<<1) | (1<<0));

	/* Enable global interrupts */
	sei();
}

uint16_t crc16_bits(uint8_t data, uint16_t seed) {
	int i, feedback;

	/*                                            Feedback
	 *   --------------------------------------------------------------------------------------X--Input
	 *   |                       |                                       |                     |
	 *  [0]->[1]->[2]->[3]->[4]->X->[5]->[6]->[7]->[8]->[9]->[10]->[11]->X->[12]->[13]->[14]->[15]
	 *
	 *   0...15 = seed
	 *   X = XOR
	 *
	 */

	for (i = 0; i < 8; i++) {
		/* Feedback from xor of input and seed MSB bits */
		feedback = ((data>>7) ^ (seed>>15)) & 0x1;
		/* If we have no feedback, we have nothing to XOR
		 * and we shift the seed normally to the left */
		if (feedback == 0) {
			seed <<= 1;
		} else {
			/* Otherwise, XOR the feedback bits onto the seed */
			seed ^= (0x10|0x800);
			/* Shift the seed */
			seed <<= 1;
			/* Append a one to the bottom of the seed */
			seed |= 0x01;
		}
		/* Shift the data to the left */
		data <<= 1;
	}

	return seed;
}

uint8_t nibble2asciihex(uint8_t nibble) {
	uint8_t ascii;

	ascii = (nibble & 0x0F) + '0';
	if (ascii > '9')
		ascii += 7;

	return ascii;
}

void UART_put_ascii_hex(uint8_t data) {
	/* Print the high nibble */
	UART_putc(nibble2asciihex((data & 0xF0) >> 4));
	/* Print the low nibble */
	UART_putc(nibble2asciihex(data));
}

void UART_put_ascii_hex_low(unsigned char data ){
	/* Print the low nibble */
	UART_putc(nibble2asciihex(data));
}

void uart_transmit_transparent(void) {
	uint16_t i;
	uint16_t seed = 0;

	/* Calculate the CRC16 of the timestamp data */
	seed = crc16_bits((adc_msHigh >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msHigh & 0xFF, seed);
	seed = crc16_bits((adc_msLow >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msLow & 0xFF, seed);

	/* Send the millisecond timestamp */
	UART_putc('T');
	UART_put_ascii_hex((adc_msHigh >> 8) & 0xFF);
	UART_put_ascii_hex(adc_msHigh & 0xFF);
	UART_put_ascii_hex((adc_msLow >> 8) & 0xFF);
	UART_put_ascii_hex(adc_msLow & 0xFF);

	/* Send the sample buffer */
	UART_putc('S');
	for (i = 0; i < ADC_SAMPLE_BUFFER_SIZE_V; i++) {
		/* Calculate the checksum of the sample data */
		seed = crc16_bits((adcSampleBuffer[i] >> 8) & 0xFF, seed);
		seed = crc16_bits(adcSampleBuffer[i] & 0xFF, seed);
		/* Send the actual data */
		UART_put_ascii_hex_low((adcSampleBuffer[i] >> 8) & 0xFF);
		UART_put_ascii_hex((adcSampleBuffer[i] & 0xFF));
		UART_putc(',');
	}
#ifdef TOGGLE
	/* was current */
	if (ADMUX & (1<<0))
		UART_putc('X');
	else
		UART_putc('Y');
#else
	UART_putc('X');
#endif

	/* Send the checksum */
	UART_put_ascii_hex((seed >> 8) & 0xFF);
	UART_put_ascii_hex(seed & 0xFF);
	UART_putc('Z');
}

void xbee_transmit_transparent(void) {
	uint16_t i;
	uint16_t seed = 0;

	/* Calculate the CRC16 of the timestamp data */
	seed = crc16_bits((adc_msHigh >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msHigh & 0xFF, seed);
	seed = crc16_bits((adc_msLow >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msLow & 0xFF, seed);

	/* Send the millisecond timestamp */
	UART_putc('T');
	UART_put_ascii_hex((adc_msHigh >> 8) & 0xFF);
	UART_put_ascii_hex(adc_msHigh & 0xFF);
	UART_put_ascii_hex((adc_msLow >> 8) & 0xFF);
	UART_put_ascii_hex(adc_msLow & 0xFF);

	/* Send the sample buffer */
	UART_putc('S');
	for (i = 0; i < ADC_SAMPLE_BUFFER_SIZE_V; i++) {
		/* Calculate the checksum of the sample data */
		seed = crc16_bits((adcSampleBuffer[i] >> 8) & 0xFF, seed);
		seed = crc16_bits(adcSampleBuffer[i] & 0xFF, seed);
		/* Send the actual data */
		UART_put_ascii_hex_low((adcSampleBuffer[i] >> 8) & 0xFF);
		UART_put_ascii_hex((adcSampleBuffer[i] & 0xFF));
		UART_putc(',');
		_delay_ms(5);
	}
#ifdef TOGGLE
	/* was current */
	if (ADMUX & (1<<0))
		UART_putc('X');
	else
		UART_putc('Y');
#else
	UART_putc('X');
#endif

	/* Send the checksum */
	UART_put_ascii_hex((seed >> 8) & 0xFF);
	UART_put_ascii_hex(seed & 0xFF);
	UART_putc('Z');
}


#ifdef XBEE_ACK

int8_t xbee_receive_ack(void) {
	uint8_t ack_response[] = {0x7E, 0x00, 0x07, 0x8B, 0x01};
	uint8_t c;
	uint8_t state = 0;
	uint16_t timeout = 1;

	while (timeout != 0) {
		/* Only block if we are actually getting worthwhile ACK data */
		if (state != 0)
			c = UART_getc();
		else
			c = UART_getc_nonblock();
		/* Ignore the 16-bit destination address, transmit retry count */
		if (state > 4 && state < 8) {
			state++;
		} else if (state == 8) {
			if (c != 0x00)
				return -1;
			else
				return 0;
		} else {
			/* Make sure we get the beginning sequence of the ACK response */
			if (c == ack_response[state])
				state++;
			else {
				state = 0;
			//	timeout++;
			}
		}
	}
	return -1;
}
#endif

void delay_ms(uint16_t duration) {
	for (; duration > 0; duration--)
		_delay_ms(1);
}

uint8_t xbee_frame_id = 0;


int8_t xbee_transmit_api_packet(uint8_t *data, uint8_t dataLen) {
	uint8_t i, retVal, checksum = 0;

	/* API Frame Start */
	UART_putc(0x7E);
	/* API Frame Length (high byte is always zero) */
	UART_putc(0);
	UART_putc(14+1+dataLen);
	/* Start of API frame data */
	/* API Frame Type: Transmit Request (0x10) */
	UART_putc(0x10);
	/* API Frame ID: 0x01 */
	UART_putc(0x01);
	/* API 64-bit Destination Address: 0 for coordinator */
	UART_putc(0); UART_putc(0); UART_putc(0); UART_putc(0);
	UART_putc(0); UART_putc(0); UART_putc(0); UART_putc(0);
	/* API 16-bit Destination Network Address: 0xFFFE for address unknown */
	UART_putc(0xFF); UART_putc(0xFE);
	/* API Broadcast Radius: 0x00 for maximum hops */
	UART_putc(0x00);
	/* API Options: 0x00 */
	UART_putc(0x00);

	checksum = (uint8_t)(0x10 + 0x01 + 0xFF + 0xFE);

	checksum += xbee_frame_id;
	UART_putc(xbee_frame_id++);

	/* API Payload Data */
	for (i = 0; i < dataLen; i++) {
		UART_putc(data[i]);
		checksum += data[i];
	}
	/* API Frame Checksum */
	UART_putc(0xFF - checksum);

	retVal = xbee_receive_ack();

	delay_ms(150);

	return retVal;
}

#define XBEE_PAYLOAD_MAX	83
uint8_t xbee_buffer[XBEE_PAYLOAD_MAX];

uint8_t _xbi_check(uint8_t xbi) {
	uint8_t timeout = 0;

	if (xbi == XBEE_PAYLOAD_MAX) {
#ifdef XBEE_ACK
		while (timeout < 5) {
			if (xbee_transmit_api_packet(xbee_buffer, xbi) == 0)
				break;
			timeout++;
		}
#else
		xbee_transmit_api_packet(xbee_buffer, xbi);
#endif
		xbi = 0;
	}
	return xbi;
}

void xbee_transmit_api(void) {
	uint16_t i;
	uint8_t xbi = 0;
	uint16_t seed = 0;

	/* Calculate the CRC16 of the timestamp data */
	seed = crc16_bits((adc_msHigh >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msHigh & 0xFF, seed);
	seed = crc16_bits((adc_msLow >> 8) & 0xFF, seed);
	seed = crc16_bits(adc_msLow & 0xFF, seed);

	/* Send the millisecond timestamp */
	xbee_buffer[xbi++] = 'T';
	xbee_buffer[xbi++] = nibble2asciihex(((adc_msHigh >> 8) & 0xFF) >> 4);
	xbee_buffer[xbi++] = nibble2asciihex((adc_msHigh >> 8) & 0xFF);
	xbee_buffer[xbi++] = nibble2asciihex((adc_msHigh & 0xFF) >> 4);
	xbee_buffer[xbi++] = nibble2asciihex(adc_msHigh & 0xFF);
	xbee_buffer[xbi++] = nibble2asciihex(((adc_msLow >> 8) & 0xFF) >> 4);
	xbee_buffer[xbi++] = nibble2asciihex((adc_msLow >> 8) & 0xFF);
	xbee_buffer[xbi++] = nibble2asciihex((adc_msLow & 0xFF) >> 4);
	xbee_buffer[xbi++] = nibble2asciihex(adc_msLow & 0xFF);

	/* Send the sample buffer */
	xbee_buffer[xbi++] = 'S';

	for (i = 0; i < ADC_SAMPLE_BUFFER_SIZE_V; i++) {
		/* Calculate the checksum of the sample data */
		seed = crc16_bits((adcSampleBuffer[i] >> 8) & 0xFF, seed);
		seed = crc16_bits(adcSampleBuffer[i] & 0xFF, seed);

		/* Send the sample data */
		xbee_buffer[xbi++] = nibble2asciihex((adcSampleBuffer[i] >> 8) & 0xFF);
		xbi = _xbi_check(xbi);
		xbee_buffer[xbi++] = nibble2asciihex((adcSampleBuffer[i] & 0xFF) >> 4);
		xbi = _xbi_check(xbi);
		xbee_buffer[xbi++] = nibble2asciihex((adcSampleBuffer[i] & 0xFF));
		xbi = _xbi_check(xbi);
		xbee_buffer[xbi++] = ',';
		xbi = _xbi_check(xbi);
	}
#ifdef TOGGLE
	/* was current */
	if (ADMUX & (1<<0))
		xbee_buffer[xbi++] = 'X';
	else
		xbee_buffer[xbi++] = 'Y';
#else
	xbee_buffer[xbi++] = 'X';
#endif

	/* Send the checksum */
	xbee_buffer[xbi++] = nibble2asciihex(((seed >> 8) & 0xFF) >> 4);
	xbi = _xbi_check(xbi);
	xbee_buffer[xbi++] = nibble2asciihex((seed >> 8) & 0xFF);
	xbi = _xbi_check(xbi);
	xbee_buffer[xbi++] = nibble2asciihex((seed & 0xFF) >> 4);
	xbi = _xbi_check(xbi);
	xbee_buffer[xbi++] = nibble2asciihex(seed & 0XFF);
	xbi = _xbi_check(xbi);
	xbee_buffer[xbi++] = 'Z';

	xbee_transmit_api_packet(xbee_buffer, xbi);
}

int main(void) {
	uint8_t xbee;

	/* Some start up time for other parts to settle */
	delay_ms(200);

	/* Initialize UART */
	UART_init(UART_calcBaudRate(9600));

	/* Enable the LEDs as outputs and clear them for now */
	DDRB |= (LED_1 | LED_2);
	PORTB |= (LED_1 | LED_2);

	/* Enable the xbee detect pin as input */
	DDRB &= ~XBEE_DETECT;

	if (PINB & XBEE_DETECT) {
		PORTB &= ~(LED_2);
		xbee = 1;
		ADC_SAMPLE_BUFFER_SIZE_V = 202+1;
	} else {
		PORTB &= ~(LED_1);
		xbee = 0;
		ADC_SAMPLE_BUFFER_SIZE_V = 404+1;
	}

	delay_ms(500);

	/* Initialize the ADC */
	ADC_init();

	while (1) {
		/* Dump the ADC sample buffer if it has been filled */
		if (adcDataReady) {
				if (xbee) {
					xbee_frame_id = 0;
					xbee_transmit_api();
					delay_ms(500);
				} else {
					uart_transmit_transparent();
				}
				adcDataReady = 0;
		}
	}

	return 0;
}
