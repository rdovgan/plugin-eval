package com.demo.booking.booking;

/** Thrown when a booking id is unknown; BookingController maps it to HTTP 404. */
public class BookingNotFoundException extends RuntimeException {

    public BookingNotFoundException(String message) {
        super(message);
    }
}
