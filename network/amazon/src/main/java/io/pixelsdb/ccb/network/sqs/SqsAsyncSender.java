package io.pixelsdb.ccb.network.sqs;

import com.google.common.util.concurrent.RateLimiter;
import io.pixelsdb.ccb.network.Sender;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;
import io.pixelsdb.pixels.storage.s3.S3;
import software.amazon.awssdk.core.internal.async.ByteBuffersAsyncRequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

import java.io.IOException;
import java.util.LinkedList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * @author hank
 * @create 2025-09-20
 */
public class SqsAsyncSender implements Sender
{
    private final S3 s3;
    private final SqsAsyncClient sqsClient;
    private final String s3Bucket;
    private final String s3Prefix;
    private final String queueUrl;
    private boolean closed = false;
    private final AtomicInteger contentId = new AtomicInteger(0);
    private final List<CompletableFuture<PutObjectResponse>> s3Responses = new LinkedList<>();
    private final RateLimiter rateLimiter = RateLimiter.create(3000d * 1024d * 1024d);

    public SqsAsyncSender(String s3Prefix, String queueUrl) throws IOException
    {
        if (!s3Prefix.endsWith("/"))
        {
            s3Prefix += "/";
        }
        this.s3Prefix = s3Prefix;
        this.s3Bucket = s3Prefix.substring(0, s3Prefix.indexOf("/"));
        this.queueUrl = queueUrl;
        this.s3 = (S3) StorageFactory.Instance().getStorage(Storage.Scheme.s3);
        this.sqsClient = SqsAsyncClient.create();
    }

    @Override
    public void send(byte[] buffer) throws IOException
    {
        this.rateLimiter.acquire(buffer.length);
        int contentId = this.contentId.getAndIncrement();
        String path = s3Prefix + contentId;
        PutObjectRequest putObjectRequest = PutObjectRequest.builder().bucket(s3Bucket).key(path).build();
        CompletableFuture<PutObjectResponse> response = this.s3.getAsyncClient()
                .putObject(putObjectRequest, ByteBuffersAsyncRequestBody.from(buffer));

        this.s3Responses.add(response.whenComplete((res, err) -> {
            if (err != null)
            {
                this.s3.reconnect();
            }
            SendMessageRequest request = SendMessageRequest.builder().queueUrl(queueUrl).messageBody(path).build();
            sqsClient.sendMessage(request).whenComplete((res0, err0) -> {
                System.out.println(res0.toString());
            });
        }));
    }

    @Override
    public boolean isClosed()
    {
        return this.closed;
    }

    @Override
    public void close() throws IOException
    {
        for (CompletableFuture<PutObjectResponse> response : this.s3Responses)
        {
            response.join();
        }
        this.sqsClient.close();
        this.closed = true;
    }
}
