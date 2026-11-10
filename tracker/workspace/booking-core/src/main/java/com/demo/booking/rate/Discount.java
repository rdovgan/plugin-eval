package com.demo.booking.rate;

import java.math.BigDecimal;

/**
 * Promotional discount, for example a promo code or a long-stay offer.
 *
 * @param code    promo code shown to the guest
 * @param percent discount in percent, 0-100
 */
public record Discount(String code, BigDecimal percent) {

    public Discount {
        if (percent.signum() < 0 || percent.compareTo(BigDecimal.valueOf(100)) > 0) {
            throw new IllegalArgumentException("Discount percent must be between 0 and 100");
        }
    }
}
