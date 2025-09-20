package io.pixelsdb.ccb.network;

import io.pixelsdb.ccb.network.sqs.SqsReceiver;
import io.pixelsdb.ccb.network.sqs.SqsSender;
import org.junit.Before;
import org.junit.Test;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * @author hank
 * @create 2025-09-20
 */
public class TestSqs
{
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final long startTime = System.currentTimeMillis();

    @Before
    public void startReceiver() throws IOException, InterruptedException
    {
        this.executor.submit(() -> {
            try (SqsReceiver receiver = new SqsReceiver("https://sqs.us-east-2.amazonaws.com/970089764833/pixels-shuffle"))
            {
                for (int i = 0; i < 8; i++)
                {
                    receiver.receive(8 * 1024 * 1024);
                }
                System.out.println("receive finished in " + (System.currentTimeMillis() - startTime) + " ms");
            } catch (IOException e)
            {
                throw new RuntimeException(e);
            }
        });
    }

    @Test
    public void sendData() throws InterruptedException
    {
        this.executor.submit(() -> {
            try
            {
                SqsSender sender = new SqsSender("pixels-turbo-intermediate/shuffle",
                        "https://sqs.us-east-2.amazonaws.com/970089764833/pixels-shuffle");
                ByteBuffer buffer = ByteBuffer.allocate(8 * 1024 * 1024);
                for (int i = 0; i < 8; i++)
                {
                    sender.send(buffer.array());
                }
                System.out.println("send finished in " + (System.currentTimeMillis() - startTime) + " ms");
            } catch (IOException e)
            {
                throw new RuntimeException(e);
            }
        });
        this.executor.shutdown();
        this.executor.awaitTermination(100, TimeUnit.HOURS);
    }
}
