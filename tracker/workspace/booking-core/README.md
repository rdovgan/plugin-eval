# booking-core

Core booking logic of the Demo booking platform: rates and discounts, bookings, cancellations and partner
notifications.

- `com.demo.booking.rate` - prices, discounts, rounding (`RateService`, `RoundingPolicy`)
- `com.demo.booking.booking` - creating and cancelling bookings (`BookingService`, `CancellationPolicy`, `BookingController`)
- `com.demo.booking.notification` - notifying partners (`PartnerNotifier`)

Documents: `docs/cancellation-rules.md`, `docs/adr/`.

Build and test: `mvn test` (Java 21).

Issues: https://github.com/demo-org/booking-core/issues
