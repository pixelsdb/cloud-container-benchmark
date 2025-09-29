package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Receiver;
import io.pixelsdb.pixels.common.physical.PhysicalReader;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import io.pixelsdb.pixels.storage.s3qs.S3QS;
import io.pixelsdb.pixels.storage.s3qs.S3Queue;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * @author hank
 * @create 2025-09-28
 */
public class S3qsReceiver implements Receiver
{
    private boolean closed = false;
    private final S3Queue queue;
    private final ExecutorService executor = Executors.newFixedThreadPool(8);

    public S3qsReceiver(String queueUrl) throws IOException
    {
        S3QS s3qs = (S3QS) StorageFactory.Instance().getStorage(Storage.Scheme.s3qs);
        this.queue = s3qs.openQueue(queueUrl);
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        this.executor.submit(() -> {
            while (true)
            {
                try (PhysicalReader reader = this.queue.poll(10))
                {
                    if (reader == null)
                    {
                        System.out.println("reader is null");
                        continue;
                    }
                    reader.readFully(bytes);
                    break;
                }
                catch (IOException e)
                {
                    e.printStackTrace();
                }
            }
        });
        return null;
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
