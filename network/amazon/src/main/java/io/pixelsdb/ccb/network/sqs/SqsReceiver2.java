package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Receiver;
import io.pixelsdb.pixels.common.physical.PhysicalReader;
import io.pixelsdb.pixels.common.physical.PhysicalReaderUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsReceiver2 implements Receiver
{
    private final Storage s3 = StorageFactory.Instance().getStorage(Storage.Scheme.s3);
    private final SqsAsyncClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;

    public SqsReceiver2(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsAsyncClient.create();
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        ReceiveMessageRequest request = ReceiveMessageRequest.builder()
            .queueUrl(queueUrl).maxNumberOfMessages(1).waitTimeSeconds(1).build();
        CompletableFuture<ReceiveMessageResponse> response = this.sqsClient.receiveMessage(request);

        response.whenComplete((res, err) -> {
            if (res.hasMessages())
            {
                String path = res.messages().getFirst().body();
                System.out.println(path);
                try (PhysicalReader reader = PhysicalReaderUtil.newPhysicalReader(this.s3, path))
                {
                    reader.readFully(bytes);
                } catch (IOException e)
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
        this.sqsClient.close();
        this.closed = true;
    }
}
