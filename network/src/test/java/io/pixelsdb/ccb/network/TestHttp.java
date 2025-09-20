package io.pixelsdb.ccb.network;

import io.pixelsdb.ccb.network.http.HttpReceiver;
import io.pixelsdb.ccb.network.http.HttpSender;
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
public class TestHttp
{
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final long startTime = System.currentTimeMillis();

    @Before
    public void startReceiver() throws IOException
    {
        this.executor.submit(() -> {
            try (HttpReceiver receiver = new HttpReceiver("localhost", 19200))
            {
                for (int i = 0; i < 1280; i++)
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
            try (HttpSender sender = new HttpSender("localhost", 19200))
            {
                ByteBuffer buffer = ByteBuffer.allocate(8 * 1024 * 1024);
                for (int i = 0; i < 1280; i++)
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
