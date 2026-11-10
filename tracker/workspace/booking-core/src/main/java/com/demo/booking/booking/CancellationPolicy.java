package com.demo.booking.booking;

/**
 * Refund rules for a cancelled booking, by the time left until check-in.
 * See docs/cancellation-rules.md.
 */
public class CancellationPolicy {

    static final long FULL_REFUND_HOURS = 48;
    static final long HALF_REFUND_HOURS = 24;

    /**
     * @param hoursBeforeCheckIn whole hours between the cancellation and the check-in time
     * @return refund in percent of the booking total
     */
    public int refundPercent(long hoursBeforeCheckIn) {
        if (hoursBeforeCheckIn >= FULL_REFUND_HOURS) {
            return 100;
        }
        if (hoursBeforeCheckIn >= HALF_REFUND_HOURS) {
            return 50;
        }
        return 0;
    }
}
