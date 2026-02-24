package com.hfusionhub;

import cn.hutool.crypto.digest.BCrypt;

public class HashGenerator {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println("Usage: java HashGenerator <password>");
            System.out.println("Example: java HashGenerator <strong-password>");
            return;
        }

        String password = args[0];
        String hash = BCrypt.hashpw(password);
        System.out.println("Password: " + password);
        System.out.println("Hash: " + hash);
        System.out.println("Verify: " + BCrypt.checkpw(password, hash));
    }
}
