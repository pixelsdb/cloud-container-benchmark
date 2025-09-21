package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Receiver;
import io.pixelsdb.pixels.common.physical.PhysicalReader;
import io.pixelsdb.pixels.common.physical.PhysicalReaderUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsReceiver implements Receiver
{
    private final Storage s3 = StorageFactory.Instance().getStorage(Storage.Scheme.s3);
    private final SqsClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;
    private final Queue<String> s3PathQueue = new ConcurrentLinkedQueue<>();
    private final ExecutorService executor = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors());

    public SqsReceiver(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsClient.create();
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        String s3Path = this.s3PathQueue.poll();
        if (s3Path == null)
        {
            ReceiveMessageResponse response;
            do
            {
                ReceiveMessageRequest request = ReceiveMessageRequest.builder()
                        .queueUrl(queueUrl).maxNumberOfMessages(10).waitTimeSeconds(1).build();
                response = this.sqsClient.receiveMessage(request);
            } while (!response.hasMessages());
            for (Message message : response.messages())
            {
                String path = message.body();
                this.s3PathQueue.add(path);
            }
            s3Path = this.s3PathQueue.poll();
        }
        String path = s3Path;
        this.executor.submit(() -> {
            System.out.println(path);
            try (PhysicalReader reader = PhysicalReaderUtil.newPhysicalReader(this.s3, path))
            {
                reader.readAsync(0, bytes);
            } catch (IOException e)
            {
                e.printStackTrace();
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
        this.sqsClient.close();
        this.closed = true;
    }
}
