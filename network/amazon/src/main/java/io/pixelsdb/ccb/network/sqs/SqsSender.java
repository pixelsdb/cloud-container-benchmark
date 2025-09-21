package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Sender;
import io.pixelsdb.pixels.common.physical.PhysicalWriter;
import io.pixelsdb.pixels.common.physical.PhysicalWriterUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsSender implements Sender
{
    private final Storage s3;
    private final SqsClient sqsClient;
    private final String s3Prefix;
    private final String queueUrl;
    private boolean closed = false;
    private AtomicInteger contentId = new AtomicInteger(0);
    private final ExecutorService executor = Executors.newFixedThreadPool(16);

    public SqsSender(String s3Prefix, String queueUrl) throws IOException
    {
        if (!s3Prefix.endsWith("/"))
        {
            s3Prefix += "/";
        }
        this.s3Prefix = s3Prefix;
        this.queueUrl = queueUrl;
        this.s3 = StorageFactory.Instance().getStorage(Storage.Scheme.s3);
        this.sqsClient = SqsClient.create();
    }

    @Override
    public void send(byte[] buffer) throws IOException
    {
        int contentId = this.contentId.getAndIncrement();
        this.executor.submit(() -> {
            String path = Storage.Scheme.s3 + "://" + s3Prefix + contentId;
            try (PhysicalWriter s3PhysicalWriter = PhysicalWriterUtil.newPhysicalWriter(s3, path, true))
            {
                s3PhysicalWriter.append(buffer, 0, buffer.length);
            } catch (IOException e)
            {
                e.printStackTrace();
            }
            SendMessageRequest request = SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody(path).build();
            SendMessageResponse response = sqsClient.sendMessage(request);
            System.out.println(response.toString());
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
        this.sqsClient.close();
        this.closed = true;
    }
}
