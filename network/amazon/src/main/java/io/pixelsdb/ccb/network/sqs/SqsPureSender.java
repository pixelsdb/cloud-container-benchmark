package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Sender;
import software.amazon.awssdk.core.SdkBytes;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.MessageAttributeValue;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * @author hank
 * @create 2025-09-29
 */
public class SqsPureSender implements Sender
{
    private final SqsClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;
    private final ExecutorService executor = Executors.newFixedThreadPool(8);

    public SqsPureSender(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsClient.create();
    }

    @Override
    public void send(byte[] buffer) throws IOException
    {
        this.executor.submit(() -> {
            Map<String, MessageAttributeValue> messageAttributeMap = Map.of(
                    "content", MessageAttributeValue.builder()
                            .binaryValue(SdkBytes.fromByteArray(buffer))
                            .dataType("Binary").build()
            );
            SendMessageRequest request = SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody("body")
                    .messageAttributes(messageAttributeMap).build();
            try
            {
                sqsClient.sendMessage(request);
            }
            catch (Throwable e)
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
        this.sqsClient.close();
        this.closed = true;
    }
}
