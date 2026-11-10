package com.demo.booking.rate;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class RateServiceTest {

    private final RateService service = new RateService(new RoundingPolicy());

    @Test
    void appliesPercentDiscount() {
        Price price = service.applyDiscount(new Price(new BigDecimal("200.00"), "EUR"),
                new Discount("SPRING10", BigDecimal.TEN));
        assertEquals(new Price(new BigDecimal("180.00"), "EUR"), price);
    }

    @Test
    void roundsHalfEvenToCents() {
        Price price = service.applyDiscount(new Price(new BigDecimal("10.125"), "EUR"),
                new Discount("NONE", BigDecimal.ZERO));
        assertEquals(new BigDecimal("10.12"), price.amount());
    }

    @Test
    void stayPriceMultipliesNightsAndRooms() {
        Price price = service.stayPrice(new Price(new BigDecimal("80.00"), "EUR"), 3, 2);
        assertEquals(new BigDecimal("480.00"), price.amount());
    }
}
