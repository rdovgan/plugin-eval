package com.demo.booking.rate;

import java.math.BigDecimal;
import java.util.Objects;

/**
 * An amount with its ISO 4217 currency code. Every price in API responses carries the currency.
 */
public record Price(BigDecimal amount, String currency) {

    public Price {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        if (currency.length() != 3) {
            throw new IllegalArgumentException("Currency must be an ISO 4217 code: " + currency);
        }
    }
}
