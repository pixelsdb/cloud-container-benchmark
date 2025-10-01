package io.pixelsdb.ccb.network;

import io.pixelsdb.ccb.network.http.HttpReceiver;
import io.pixelsdb.ccb.network.http.HttpSender;
import io.pixelsdb.ccb.network.sqs.S3qsReceiver;
import io.pixelsdb.ccb.network.sqs.S3qsSender;
import io.pixelsdb.pixels.common.exception.TransException;
import io.pixelsdb.pixels.common.transaction.TransContext;
import io.pixelsdb.pixels.common.transaction.TransService;

import java.io.IOException;
import java.util.LinkedList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * @author hank
 * @create 2025-09-20
 */
public class Main
{
    private static final int BUFFER_SIZE = 8 * 1024 * 1024;
    private static final long BUFFER_NUM = 12800;
    public static void main(String[] args) throws IOException, InterruptedException
    {
        if (args.length < 2)
        {
            System.out.println("Usage: program[sender/receiver] method[http/sqs] args");
            return;
        }
        String program = args[0];
        String method = args[1];

        if (program.equals("sender"))
        {
            Sender sender;
            if (method.equals("http"))
            {
                String host = args[2];
                String port = args[3];
                sender = new HttpSender(host, Integer.parseInt(port));
            }
            else if (method.equals("sqs"))
            {
                String s3Prefix = args[2];
                String queueUrl = args[3];
                sender = new S3qsSender(s3Prefix, queueUrl);
            }
            else
            {
                System.err.println("Unknown method: " + method);
                return;
            }
            byte[] smallBuffer = new byte[BUFFER_SIZE];
            sender.send(smallBuffer);
            long start = System.currentTimeMillis();
            byte[] buffer = new byte[BUFFER_SIZE];
            for (int i = 0; i < BUFFER_NUM; ++i)
            {
                sender.send(buffer);
            }
            sender.close();
            long end = System.currentTimeMillis();
            System.out.println("latency: " + (end - start)/1000.0d + " seconds");
            System.out.println("rate: " + BUFFER_SIZE * BUFFER_NUM * 1000.0d / 1024 / 1024 / (end - start) + " MB/s");
            System.out.println("start at: " + start);
            System.out.println("stop at: " + end);
        }
        else if (program.equals("receiver"))
        {
            Receiver receiver;
            if (method.equals("http"))
            {
                String host = args[2];
                String port = args[3];
                receiver = new HttpReceiver(host, Integer.parseInt(port));
            }
            else if (method.equals("sqs"))
            {
                String queueUrl = args[2];
                receiver = new S3qsReceiver(queueUrl);
            }
            else
            {
                System.err.println("Unknown method: " + method);
                return;
            }
            receiver.receive(BUFFER_SIZE);
            long start = System.currentTimeMillis();
            for (int i = 0; i < BUFFER_NUM; ++i)
            {
                receiver.receive(BUFFER_SIZE);
            }
            receiver.close();
            long end = System.currentTimeMillis();
            System.out.println("latency: " + (end - start)/1000.0d + " seconds");
            System.out.println("rate: " + BUFFER_SIZE * BUFFER_NUM * 1000.0d / 1024 / 1024 / (end - start) + " MB/s");
            System.out.println("start at: " + start);
            System.out.println("stop at: " + end);
        }
        else if (program.equals("trans"))
        {
            TransService transService = TransService.CreateInstance("10.77.110.37", 18889);
            ExecutorService executorService = Executors.newFixedThreadPool(64);
            for (int i = 0; i < 64; i++)
            {
                executorService.submit(() -> {
                    List<TransContext> contexts = new LinkedList<>();
                    long start = System.currentTimeMillis();
                    for (int j = 0; j < 10240; j++)
                    {
                        try
                        {
                            TransContext context = transService.beginTrans(false);
                            contexts.add(context);
                        } catch (TransException e)
                        {
                            throw new RuntimeException(e);
                        }
                    }
                    System.out.println(System.currentTimeMillis() - start);

                    start = System.currentTimeMillis();
                    for (TransContext context : contexts)
                    {
                        try
                        {
                            transService.commitTrans(context.getTransId(), context.getTimestamp());
                        } catch (TransException e)
                        {
                            throw new RuntimeException(e);
                        }
                    }
                    System.out.println(System.currentTimeMillis() - start);
                });
            }
            executorService.shutdown();
            executorService.awaitTermination(10, TimeUnit.HOURS);
        }
        else
        {
            System.err.println("Unknown program: " + program);
        }
    }
}
