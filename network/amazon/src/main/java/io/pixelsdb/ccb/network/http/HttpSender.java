package io.pixelsdb.ccb.network.http;

import io.pixelsdb.ccb.network.Sender;
import io.pixelsdb.pixels.common.physical.PhysicalWriter;
import io.pixelsdb.pixels.common.physical.PhysicalWriterUtil;
import io.pixelsdb.pixels.common.physical.Storage;
import io.pixelsdb.pixels.common.physical.StorageFactory;

import java.io.IOException;

/**
 * @author hank
 * @create 2025-09-20
 */
public class HttpSender implements Sender
{
    private final PhysicalWriter physicalWriter;
    private boolean closed = false;

    public HttpSender(String host, int port) throws IOException
    {
        Storage httpStream = StorageFactory.Instance().getStorage(Storage.Scheme.httpstream);
        String path = Storage.Scheme.httpstream + "://" + host + ":" + port;
        this.physicalWriter = PhysicalWriterUtil.newPhysicalWriter(httpStream, path);
    }
    @Override
    public void send(byte[] buffer) throws IOException
    {
        this.physicalWriter.append(buffer, 0, buffer.length);
        this.physicalWriter.flush();
    }

    @Override
    public boolean isClosed()
    {
        return this.closed;
    }

    @Override
    public void close() throws IOException
    {
        this.physicalWriter.close();
        this.closed = true;
    }
}
