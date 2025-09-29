package io.pixelsdb.ccb.network;

import io.pixelsdb.ccb.network.http.HttpReceiver;
import io.pixelsdb.ccb.network.http.HttpSender;
import io.pixelsdb.ccb.network.sqs.SqsPureReceiver;
import io.pixelsdb.ccb.network.sqs.SqsPureSender;

import java.io.IOException;

/**
 * @author hank
 * @create 2025-09-20
 */
public class Main
{
    private static final int BUFFER_SIZE = 1 * 1000 * 1000;
    private static final long BUFFER_NUM = 12800 * 8;
    public static void main(String[] args) throws IOException
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
                sender = new SqsPureSender(queueUrl);
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
                receiver = new SqsPureReceiver(queueUrl);
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
        else
        {
            System.err.println("Unknown program: " + program);
        }
    }
}
