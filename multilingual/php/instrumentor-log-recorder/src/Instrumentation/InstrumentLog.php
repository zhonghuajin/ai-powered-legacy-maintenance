<?php

namespace App\Instrumentation;

$localAutoload = dirname(__DIR__) . '/vendor/autoload.php';
if (file_exists($localAutoload)) {
    require_once $localAutoload;
}

class InstrumentLog {
    private static $redis = null;
    private static $pid = null;

    private static function getRedis() {
        if (self::$redis === null) {
            try {
                self::$redis = new \Predis\Client([
                    'scheme' => 'tcp',
                    'host'   => '127.0.0.1',
                    'port'   => 6379,
                ]);
            } catch (\Exception $e) {
                error_log("[InstrumentLog] Redis connection failed: " . $e->getMessage());
            }
        }
        return self::$redis;
    }

    private static function getPid() {
        if (self::$pid === null) {
            self::$pid = getmypid();
            $redis = self::getRedis();
            if ($redis) {
                $redis->rpush('instrumentor:pids_order', [self::$pid]);
            }
        }
        return self::$pid;
    }

    public static function staining($message) {
        $redis = self::getRedis();
        if (!$redis) {
            return;
        }

        $pid = self::getPid();
        $key = 'instrumentor:log:' . $pid;
        
        $redis->rpush($key, [$message]);
    }
}