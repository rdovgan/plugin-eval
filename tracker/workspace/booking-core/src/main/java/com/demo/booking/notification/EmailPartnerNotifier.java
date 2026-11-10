package com.demo.booking.notification;

import com.demo.booking.booking.Booking;
import com.demo.booking.rate.Price;
import java.util.logging.Logger;

/**
 * The only PartnerNotifier today: sends an email to the partner's contact address.
 * Delivery is fire-and-forget, without retries.
 */
public class EmailPartnerNotifier implements PartnerNotifier {

    private static final Logger LOG = Logger.getLogger(EmailPartnerNotifier.class.getName());

    private final MailGateway mail;

    public EmailPartnerNotifier(MailGateway mail) {
        this.mail = mail;
    }

    @Override
    public void bookingCancelled(Booking booking, Price refund) {
        String body = "Booking " + booking.id() + " was cancelled. Refund: " + refund.amount() + " " + refund.currency();
        mail.send(booking.partnerId(), "Booking cancelled", body);
        LOG.info(() -> "Partner notified about cancellation of " + booking.id());
    }

    /** Thin wrapper over the SMTP client; resolves the partner's contact address by partner id. */
    public interface MailGateway {
        void send(String partnerId, String subject, String body);
    }
}
