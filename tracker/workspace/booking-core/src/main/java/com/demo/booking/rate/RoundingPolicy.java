package com.demo.booking.rate;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Rounding of every amount shown to a guest or sent to a partner.
 * See docs/adr/0003-price-rounding.md.
 */
public class RoundingPolicy {

    static final int SCALE = 2;
    static final RoundingMode MODE = RoundingMode.HALF_EVEN;

    public BigDecimal round(BigDecimal amount) {
        return amount.setScale(SCALE, MODE);
    }
}
