package io.pixelsdb.ccb.network;

import io.pixelsdb.ccb.network.sqs.SqsPureReceiver;
import io.pixelsdb.ccb.network.sqs.SqsPureSender;
import org.junit.Test;

import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * @author hank
 * @create 2025-09-29
 */
public class TestPureSqs
{
    @Test
    public void testReceiver() throws IOException
    {
        Receiver receiver = new SqsPureReceiver("https://sqs.us-east-2.amazonaws.com/970089764833/pixels-shuffle");
        ByteBuffer buffer = receiver.receive(1024*1000);
        System.out.println(buffer.capacity());
        receiver.close();
    }

    @Test
    public void testSender() throws IOException
    {
        Sender sender = new SqsPureSender("https://sqs.us-east-2.amazonaws.com/970089764833/pixels-shuffle");
        sender.send(new byte[1024*1000]);
        sender.close();
    }
}
