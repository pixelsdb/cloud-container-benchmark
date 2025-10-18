package io.pixelsdb.ccb.network;

import com.google.protobuf.ByteString;
import io.pixelsdb.ccb.network.http.HttpReceiver;
import io.pixelsdb.ccb.network.http.HttpSender;
import io.pixelsdb.ccb.network.sqs.S3qsReceiver;
import io.pixelsdb.ccb.network.sqs.S3qsSender;
import io.pixelsdb.pixels.common.exception.IndexException;
import io.pixelsdb.pixels.common.index.IndexService;
import io.pixelsdb.pixels.common.index.IndexServiceProvider;
import io.pixelsdb.pixels.common.transaction.TransContext;
import io.pixelsdb.pixels.common.transaction.TransService;
import io.pixelsdb.pixels.index.IndexProto;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * @author hank
 * @create 2025-09-20
 */
public class Main
{
    private static final int BUFFER_SIZE = 8 * 1024 * 1024;
    private static final long BUFFER_NUM = 12800;
    public static void main(String[] args) throws IOException, InterruptedException, IndexException
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
            ExecutorService executorService = Executors.newCachedThreadPool();
            for (int i = 0; i < 128; i++)
            {
                executorService.submit(() -> {
                    try
                    {
                        long beginTime = 0, commitTime = 0;
                        for (int j = 0; j < 100; j++)
                        {
                            try
                            {
                                long start = System.currentTimeMillis();
                                List<TransContext> contexts = transService.beginTransBatch(100, false);
                                beginTime += System.currentTimeMillis() - start;
                                if (contexts.size() != 100)
                                {
                                    System.out.println(contexts.size());
                                }
                                List<Long> transIds = new ArrayList<>(100);
                                for (TransContext context : contexts)
                                {
                                    transIds.add(context.getTransId());
                                }
                                start = System.currentTimeMillis();
                                List<Boolean> success = transService.commitTransBatch(transIds, false);
                                commitTime += System.currentTimeMillis() - start;
                                for (int k = 0; k < 100; k++)
                                {
                                    if (!success.get(k))
                                    {
                                        System.out.println("transaction " + contexts.get(k).getTransId() + " failed to commit");
                                    }
                                }
                            } catch (Exception e)
                            {
                                throw new RuntimeException(e);
                            }
                        }
                        System.out.println("begin trans cost: " + beginTime + ", commit trans cost: " + commitTime);
                    } catch (Exception e)
                    {
                        throw new RuntimeException(e);
                    }
                });
            }
            executorService.shutdown();
            executorService.awaitTermination(10, TimeUnit.HOURS);
        }
        else if (program.equals("index"))
        {
            int threadNum = Integer.parseInt(args[1]);
            int batchNum = Integer.parseInt(args[2]);
            int batchSize = Integer.parseInt(args[3]);
            long tableId = Long.parseLong(args[4]);
            long indexId = Long.parseLong(args[5]);
            IndexService indexService = IndexServiceProvider.getService(IndexServiceProvider.ServiceMode.local);
            ExecutorService executorService = Executors.newFixedThreadPool(threadNum);
            indexService.openIndex(tableId, indexId, true);
            AtomicLong rowKeyPostfix = new AtomicLong(0);
            AtomicLong transTimestamp = new AtomicLong(1);
            long startGlobal = System.currentTimeMillis();
            for (int i = 0; i < threadNum; i++)
            {
                long finalI = i;
                executorService.submit(() -> {
                    long start = System.currentTimeMillis();
                    for (int j = 0; j < batchNum; j++)
                    {
                        try
                        {
                            long timestamp = transTimestamp.getAndIncrement();
                            IndexProto.RowIdBatch batch = indexService.allocateRowIdBatch(tableId, batchSize);
                            List<IndexProto.PrimaryIndexEntry> primaryIndexEntries = new ArrayList<>(batchSize);
                            for (int k = 0; k < batch.getLength(); k++)
                            {
                                long rowId = batch.getRowIdStart() + k;
                                // build a unique row key = 'key-{rowId}'
                                IndexProto.IndexKey indexKey = IndexProto.IndexKey.newBuilder()
                                        .setTableId(tableId).setIndexId(indexId).setTimestamp(timestamp)
                                        .setKey(ByteString.copyFrom("key-" + rowKeyPostfix.getAndIncrement(), StandardCharsets.UTF_8)).build();
                                // set the row location to the i*bathNum+j th file, the first row group, and the j*batchSize+k row.
                                IndexProto.RowLocation rowLocation = IndexProto.RowLocation.newBuilder().setFileId(finalI * batchNum + j)
                                        .setRgId(0).setRgRowOffset(j * batchSize + k).build();
                                primaryIndexEntries.add(IndexProto.PrimaryIndexEntry.newBuilder().setRowId(rowId)
                                        .setIndexKey(indexKey).setRowLocation(rowLocation).build());
                            }
                            indexService.putPrimaryIndexEntries(tableId, indexId, primaryIndexEntries);
                        } catch (IndexException e)
                        {
                            e.printStackTrace();
                        }
                    }
                    long end = System.currentTimeMillis();
                    System.out.println("elapsed time: " + (end - start) + " ms");
                    System.out.println("throughput: " + ((double) batchNum * batchSize) * 1000.0d / (end - start) + " ops");
                });
            }
            executorService.shutdown();
            executorService.awaitTermination(10, TimeUnit.HOURS);
            indexService.closeIndex(tableId, indexId, true);
            long endGlobal = System.currentTimeMillis();
            System.out.println("put elapsed time: " + (endGlobal - startGlobal) + " ms");
            System.out.println("put throughput: " + ((double) threadNum * batchNum * batchSize) * 1000.0d / (endGlobal - startGlobal) + " ops");

            executorService = Executors.newFixedThreadPool(threadNum);
            indexService.openIndex(tableId, indexId, true);
            rowKeyPostfix.set(0);
            startGlobal = System.currentTimeMillis();
            for (int i = 0; i < threadNum; i++)
            {
                executorService.submit(() -> {
                    long start = System.currentTimeMillis();
                    for (int j = 0; j < batchNum; j++)
                    {
                        long timestamp = transTimestamp.getAndIncrement();
                        List<IndexProto.IndexKey> indexKeys = new ArrayList<>(batchSize);
                        for (int k = 0; k < batchSize; k++)
                        {
                            // build a unique row key = 'key-{rowId}'
                            IndexProto.IndexKey indexKey = IndexProto.IndexKey.newBuilder()
                                    .setTableId(tableId).setIndexId(indexId).setTimestamp(timestamp)
                                    .setKey(ByteString.copyFrom("key-" + rowKeyPostfix.getAndIncrement(), StandardCharsets.UTF_8)).build();
                            indexKeys.add(indexKey);
                        }
                        try
                        {
                            indexService.deletePrimaryIndexEntries(tableId, indexId, indexKeys);
                        } catch (IndexException e)
                        {
                            e.printStackTrace();
                        }
                    }
                    long end = System.currentTimeMillis();
                    System.out.println("elapsed time: " + (end - start) + " ms");
                    System.out.println("throughput: " + ((double) batchNum * batchSize) * 1000.0d / (end - start) + " ops");
                });
            }
            executorService.shutdown();
            executorService.awaitTermination(10, TimeUnit.HOURS);
            indexService.closeIndex(tableId, indexId, true);
            endGlobal = System.currentTimeMillis();
            System.out.println("delete elapsed time: " + (endGlobal - startGlobal) + " ms");
            System.out.println("delete throughput: " + ((double) threadNum * batchNum * batchSize) * 1000.0d / (endGlobal - startGlobal) + " ops");
        }
        else
        {
            System.err.println("Unknown program: " + program);
        }
    }
}
