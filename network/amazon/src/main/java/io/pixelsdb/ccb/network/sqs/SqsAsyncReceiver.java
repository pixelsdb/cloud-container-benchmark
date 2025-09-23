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
import java.util.LinkedList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsAsyncReceiver implements Receiver
{
    private final Storage s3 = StorageFactory.Instance().getStorage(Storage.Scheme.s3);
    private final SqsClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;
    private final List<CompletableFuture<Void>> s3Responses = new LinkedList<>();

    public SqsAsyncReceiver(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsClient.create();
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        ReceiveMessageRequest request = ReceiveMessageRequest.builder()
            .queueUrl(queueUrl).maxNumberOfMessages(10).waitTimeSeconds(20).build();
        ReceiveMessageResponse response = this.sqsClient.receiveMessage(request);
        if (response.hasMessages())
        {
            for (Message message : response.messages())
            {
                String path = message.body();
                try (PhysicalReader reader = PhysicalReaderUtil.newPhysicalReader(this.s3, path))
                {
                    this.s3Responses.add(reader.readAsync(0, bytes).thenAccept(buf -> {
                        System.out.println(path);
                    }));
                } catch (IOException e)
                {
                    e.printStackTrace();
                }
            }
        }
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
        for (CompletableFuture<Void> response : this.s3Responses)
        {
            response.join();
        }
        this.sqsClient.close();
        this.closed = true;
    }
}
