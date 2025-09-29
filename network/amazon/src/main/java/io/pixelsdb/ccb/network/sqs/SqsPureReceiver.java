package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Receiver;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.concurrent.*;

/**
 * @author hank
 * @create 2025-09-29
 */
public class SqsPureReceiver implements Receiver
{
    private final SqsClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;
    private final BlockingQueue<ByteBuffer> contentQueue = new LinkedBlockingQueue<>();
    private final ExecutorService executor = Executors.newCachedThreadPool();

    public SqsPureReceiver(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsClient.create();
        for (int i = 0; i < 8; ++i)
        {
            this.executor.submit(() -> {
                while (!closed)
                {
                    ReceiveMessageRequest request = ReceiveMessageRequest.builder()
                            .queueUrl(queueUrl).maxNumberOfMessages(10).waitTimeSeconds(5).build();
                    ReceiveMessageResponse response = this.sqsClient.receiveMessage(request);
                    if (!response.hasMessages())
                    {
                        for (Message message : response.messages())
                        {
                            String content = message.body();
                            this.contentQueue.add(ByteBuffer.wrap(content.getBytes()));
                        }
                    }
                }
            });
        }
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        try
        {
            return this.contentQueue.take();
        }
        catch (InterruptedException e)
        {
            throw new IOException(e);
        }
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
        this.closed = true;
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

    }
}
