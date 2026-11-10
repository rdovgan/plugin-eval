package com.demo.booking.notification;

import com.demo.booking.booking.Booking;
import com.demo.booking.rate.Price;

/** Tells the partner (the channel the booking came from) about changes to a booking. */
public interface PartnerNotifier {

    void bookingCancelled(Booking booking, Price refund);
}
