package com.demo.booking.rate;

import java.math.BigDecimal;

/**
 * Calculates the price a guest pays for a stay.
 */
public class RateService {

    private final RoundingPolicy rounding;

    public RateService(RoundingPolicy rounding) {
        this.rounding = rounding;
    }

    /**
     * Applies a promotional discount to the base price of a stay.
     *
     * @param basePrice price before discounts, in the booking currency
     * @param discount  promotional discount of the booking
     * @return the discounted price, rounded by {@link RoundingPolicy}
     */
    public Price applyDiscount(Price basePrice, Discount discount) {
        BigDecimal factor = BigDecimal.ONE.subtract(discount.percent().movePointLeft(2));
        BigDecimal discounted = basePrice.amount().multiply(factor);
        return new Price(rounding.round(discounted), basePrice.currency());
    }

    /**
     * Price of a stay: nightly rate times nights times rooms.
     */
    public Price stayPrice(Price nightlyRate, int nights, int rooms) {
        BigDecimal total = nightlyRate.amount()
                .multiply(BigDecimal.valueOf(nights))
                .multiply(BigDecimal.valueOf(rooms));
        return new Price(rounding.round(total), nightlyRate.currency());
    }
}
