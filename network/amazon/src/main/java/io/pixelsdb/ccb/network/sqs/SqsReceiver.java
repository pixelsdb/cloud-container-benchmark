package io.pixelsdb.ccb.network.sqs;

import io.pixelsdb.ccb.network.Receiver;
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
        System.out.println(s3Path);
        //try (PhysicalReader reader = PhysicalReaderUtil.newPhysicalReader(this.s3, s3Path))
        {
            //return reader.readFully(bytes);
            return null;
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
        this.sqsClient.close();
        this.closed = true;
    }
}
