package com.demo.booking.booking;

import com.demo.booking.rate.Price;

/**
 * REST entry points (framework annotations omitted in this module):
 * <ul>
 *   <li>{@code POST /bookings} - {@link #create}</li>
 *   <li>{@code GET /bookings/{id}} - {@link #get}</li>
 *   <li>{@code POST /bookings/{id}/cancel} - {@link #cancel}</li>
 * </ul>
 * IllegalArgumentException maps to 400, BookingNotFoundException to 404.
 */
public class BookingController {

    private final BookingService service;

    public BookingController(BookingService service) {
        this.service = service;
    }

    public BookingResponse create(BookingService.BookingRequest request) {
        return BookingResponse.of(service.create(request));
    }

    public BookingResponse get(String id) {
        return BookingResponse.of(service.find(id));
    }

    public Price cancel(String id) {
        return service.cancel(id);
    }

    /** Response body. {@code total} carries amount and currency (added in #260). */
    public record BookingResponse(String id, String status, int nights, int rooms, Price total) {
        static BookingResponse of(Booking b) {
            return new BookingResponse(b.id(), b.status().name(), b.nights(), b.rooms(), b.total());
        }
    }
}
