package com.demo.booking.booking;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CancellationPolicyTest {

    private final CancellationPolicy policy = new CancellationPolicy();

    @Test
    void fullRefundFromFortyEightHours() {
        assertEquals(100, policy.refundPercent(48));
        assertEquals(100, policy.refundPercent(200));
    }

    @Test
    void halfRefundBetweenTwentyFourAndFortyEightHours() {
        assertEquals(50, policy.refundPercent(47));
        assertEquals(50, policy.refundPercent(24));
    }

    @Test
    void noRefundUnderTwentyFourHours() {
        assertEquals(0, policy.refundPercent(23));
    }
}
