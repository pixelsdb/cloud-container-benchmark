package io.pixelsdb.ccb.network.sqs;

import com.google.common.util.concurrent.RateLimiter;
import io.pixelsdb.ccb.network.Receiver;
import io.pixelsdb.pixels.common.physical.PhysicalReader;
import io.pixelsdb.pixels.common.physical.PhysicalReaderUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.Queue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsAsyncReceiver implements Receiver
{
    private final Storage s3 = StorageFactory.Instance().getStorage(Storage.Scheme.s3);
    private final SqsAsyncClient sqsClient;
    private final String queueUrl;
    private boolean closed = false;
    private final Queue<CompletableFuture<ReceiveMessageResponse>> sqsResponses = new ConcurrentLinkedQueue<>();
    private final Queue<CompletableFuture<Void>> s3Responses = new ConcurrentLinkedQueue<>();
    private final RateLimiter rateLimiter = RateLimiter.create(3000d * 1024d * 1024d);

    public SqsAsyncReceiver(String queueUrl) throws IOException
    {
        this.queueUrl = queueUrl;
        this.sqsClient = SqsAsyncClient.create();
    }

    @Override
    public ByteBuffer receive(int bytes) throws IOException
    {
        ReceiveMessageRequest request = ReceiveMessageRequest.builder()
            .queueUrl(queueUrl).maxNumberOfMessages(10).waitTimeSeconds(20).build();
        this.sqsResponses.add(this.sqsClient.receiveMessage(request).whenComplete((response, err) -> {
            if (err != null)
            {
                err.printStackTrace();
                return;
            }
            if (response.hasMessages())
            {
                for (Message message : response.messages())
                {
                    String path = message.body();
                    this.rateLimiter.acquire(bytes);
                    try (PhysicalReader reader = PhysicalReaderUtil.newPhysicalReader(this.s3, path))
                    {
                        CompletableFuture<Void> future = new CompletableFuture<>();
                        this.s3Responses.add(future);
                        reader.readAsync(0, bytes).whenComplete((buf, err0) -> {
                            System.out.println(path);
                            future.complete(null);
                        });
                    } catch (IOException e)
                    {
                        e.printStackTrace();
                    }
                }
            }
        }));
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
        for (CompletableFuture<ReceiveMessageResponse> response : this.sqsResponses)
        {
            response.join();
        }
        for (CompletableFuture<Void> response : this.s3Responses)
        {
            response.join();
        }
        this.sqsClient.close();
        this.closed = true;
    }
}
