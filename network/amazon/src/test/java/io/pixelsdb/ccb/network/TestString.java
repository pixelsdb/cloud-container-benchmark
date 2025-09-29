package io.pixelsdb.ccb.network;

import org.junit.Test;

import java.nio.charset.StandardCharsets;

/**
 * @author hank
 * @create 2025-09-29
 */
public class TestString
{
    @Test
    public void test()
    {
        byte[] buffer = new byte[1024];
        String string = new String(buffer, StandardCharsets.UTF_8);
        System.out.println(string.length());
    }
}
