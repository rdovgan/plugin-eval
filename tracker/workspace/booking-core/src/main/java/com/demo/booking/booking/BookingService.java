package com.demo.booking.booking;

import com.demo.booking.notification.PartnerNotifier;
import com.demo.booking.rate.Discount;
import com.demo.booking.rate.Price;
import com.demo.booking.rate.RateService;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.logging.Logger;

/**
 * Creates and cancels bookings. Storage is the {@code booking} table (see BookingRepository in the
 * persistence module); kept in memory here.
 */
public class BookingService {

    private static final Logger LOG = Logger.getLogger(BookingService.class.getName());

    /** Maximum rooms in one booking. Larger requests go through sales. */
    static final int MAX_ROOMS = 10;

    private final RateService rates;
    private final CancellationPolicy cancellationPolicy;
    private final PartnerNotifier partnerNotifier;
    private final Clock clock;
    private final Map<String, Booking> bookings = new HashMap<>();

    public BookingService(RateService rates, CancellationPolicy cancellationPolicy,
                          PartnerNotifier partnerNotifier, Clock clock) {
        this.rates = rates;
        this.cancellationPolicy = cancellationPolicy;
        this.partnerNotifier = partnerNotifier;
        this.clock = clock;
    }

    public Booking create(BookingRequest request) {
        if (request.nights() <= 0) {
            throw new IllegalArgumentException("Booking must have at least one night");
        }
        if (request.rooms() <= 0 || request.rooms() > MAX_ROOMS) {
            throw new IllegalArgumentException("Rooms per booking must be between 1 and " + MAX_ROOMS);
        }
        Price stay = rates.stayPrice(request.nightlyRate(), request.nights(), request.rooms());
        Price total = rates.applyDiscount(stay, request.discount());
        Booking booking = new Booking(UUID.randomUUID().toString(), request.propertyId(), request.partnerId(),
                request.checkIn(), request.nights(), request.rooms(), request.discount(), total);
        bookings.put(booking.id(), booking);
        LOG.info(() -> "Booking created: " + booking.id());
        return booking;
    }

    /**
     * Cancels a booking and returns the refund for the guest.
     */
    public Price cancel(String bookingId) {
        Booking booking = find(bookingId);
        long hoursBefore = Duration.between(LocalDateTime.now(clock), booking.checkIn()).toHours();
        int refundPercent = cancellationPolicy.refundPercent(hoursBefore);
        BigDecimal refund = booking.total().amount()
                .multiply(BigDecimal.valueOf(refundPercent))
                .movePointLeft(2);
        booking.cancel();
        Price refundPrice = new Price(refund, booking.total().currency());
        partnerNotifier.bookingCancelled(booking, refundPrice);
        return refundPrice;
    }

    public Booking find(String bookingId) {
        Booking booking = bookings.get(bookingId);
        if (booking == null) {
            throw new BookingNotFoundException("Booking not foud: " + bookingId);
        }
        return booking;
    }

    /** Request to create a booking, as received by BookingController. */
    public record BookingRequest(String propertyId, String partnerId, LocalDateTime checkIn, int nights,
                                 int rooms, Price nightlyRate, Discount discount) {
    }
}
