package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Sender;
import io.pixelsdb.pixels.common.physical.PhysicalWriter;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import io.pixelsdb.pixels.storage.s3qs.S3QS;
import io.pixelsdb.pixels.storage.s3qs.S3Queue;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * @author hank
 * @create 2025-09-28
 */
public class S3qsSender implements Sender
{
    private final String s3Prefix;
    private final S3Queue queue;
    private final AtomicInteger contentId = new AtomicInteger(0);
    private final ExecutorService executor = Executors.newFixedThreadPool(8);
    private boolean closed = false;

    public S3qsSender(String s3Prefix, String queueUrl) throws IOException
    {
        if (!s3Prefix.endsWith("/"))
        {
            s3Prefix += "/";
        }
        this.s3Prefix = s3Prefix;
        S3QS s3qs = (S3QS) StorageFactory.Instance().getStorage(Storage.Scheme.s3qs);
        this.queue = s3qs.openQueue(queueUrl);
    }

    @Override
    public void send(byte[] buffer) throws IOException
    {
        int contentId = this.contentId.getAndIncrement();
        this.executor.submit(() -> {
            String path = s3Prefix + contentId;
            try (PhysicalWriter writer = this.queue.offer(path))
            {
                writer.append(buffer);
            }
            catch (IOException e)
            {
                e.printStackTrace();
            }
        });
    }

    @Override
    public boolean isClosed()
    {
        return this.closed;
    }

    @Override
    public void close() throws IOException
    {
        this.executor.shutdown();
        while (true)
        {
            try
            {
                if (this.executor.awaitTermination(1, TimeUnit.SECONDS))
                {
                    break;
                }
            } catch (InterruptedException e)
            {
                e.printStackTrace();
            }
        }
        this.queue.close();
        this.closed = true;
    }
}
