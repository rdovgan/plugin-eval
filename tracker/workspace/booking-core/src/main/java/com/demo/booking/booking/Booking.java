package com.demo.booking.booking;

import com.demo.booking.rate.Discount;
import com.demo.booking.rate.Price;
import java.time.LocalDateTime;

/**
 * A guest's booking of one or more rooms in one property.
 */
public class Booking {

    public enum Status { CONFIRMED, CANCELLED }

    private final String id;
    private final String propertyId;
    private final String partnerId;
    private final LocalDateTime checkIn;
    private final int nights;
    private final int rooms;
    private final Discount discount;
    private final Price total;
    private Status status = Status.CONFIRMED;

    public Booking(String id, String propertyId, String partnerId, LocalDateTime checkIn,
                   int nights, int rooms, Discount discount, Price total) {
        this.id = id;
        this.propertyId = propertyId;
        this.partnerId = partnerId;
        this.checkIn = checkIn;
        this.nights = nights;
        this.rooms = rooms;
        this.discount = discount;
        this.total = total;
    }

    public String id() { return id; }
    public String propertyId() { return propertyId; }
    public String partnerId() { return partnerId; }
    public LocalDateTime checkIn() { return checkIn; }
    public int nights() { return nights; }
    public int rooms() { return rooms; }
    public Discount discount() { return discount; }
    public Price total() { return total; }
    public Status status() { return status; }

    void cancel() { this.status = Status.CANCELLED; }
}
