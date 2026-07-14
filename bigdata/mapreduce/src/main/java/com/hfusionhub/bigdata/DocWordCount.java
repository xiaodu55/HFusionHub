package com.hfusionhub.bigdata;

import java.io.IOException;
import java.util.StringTokenizer;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.IntWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

/**
 * HFusionData Analytics — 经典 MapReduce 示例:知识库文档词频统计。
 *
 * <p>输入: ODS 文本目录(每行一个分片文本,由 jsonl_to_hdfs/全量链路落地);
 * 输出: word \t count,下游可按 TF-IDF 生成"文档关键词"表,反哺 AI 平台的
 * 文档画像(与 RAG 检索的 outline/keyword 召回呼应)。</p>
 *
 * <p>答辩要点: shuffle 按 key 分区与排序、combiner 本地聚合降低网络传输、
 * mapper/reducer 内存与 vcores 的 mapred-site 联动。</p>
 */
public class DocWordCount {

    /** 中文按字 + 英文按词的轻量分词:满足演示口径,生产可换 IK/jieba。 */
    static class TokenizerMapper extends Mapper<Object, Text, Text, IntWritable> {

        private static final IntWritable ONE = new IntWritable(1);
        private final Text word = new Text();

        @Override
        public void map(Object key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString();
            StringTokenizer englishWords = new StringTokenizer(line,
                    " \t\r\n\f.,;:!?()[]{}<>/\\|@#$%^&*+=~`\"'“”‘’、。,;:!?()【】《》—…");
            while (englishWords.hasMoreTokens()) {
                String token = englishWords.nextToken().toLowerCase();
                if (token.length() >= 2 && token.chars().allMatch(c -> c < 0x2e80)) {
                    // 英文/数字词(含下划线连接)按整词
                    word.set(token);
                    context.write(word, ONE);
                } else {
                    // CJK 文本按双字切分(bigram),保留中文语义
                    for (int i = 0; i + 1 < token.length(); i++) {
                        String bigram = token.substring(i, i + 2);
                        if (bigram.matches(".*[\\u2e80-\\u9fff\\uf900-\\ufaff].*")) {
                            word.set(bigram);
                            context.write(word, ONE);
                        }
                    }
                }
            }
        }
    }

    /** Combiner 与 Reducer 同实现:map 端本地预聚合,显著减少 shuffle 数据量。 */
    static class SumReducer extends Reducer<Text, IntWritable, Text, IntWritable> {

        private final IntWritable total = new IntWritable();

        @Override
        public void reduce(Text key, Iterable<IntWritable> values, Context context)
                throws IOException, InterruptedException {
            int sum = 0;
            for (IntWritable v : values) {
                sum += v.get();
            }
            total.set(sum);
            context.write(key, total);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("用法: DocWordCount <输入路径> <输出路径>");
            System.exit(2);
        }
        Configuration conf = new Configuration();
        Job job = Job.getInstance(conf, "hfusion-doc-wordcount");
        job.setJarByClass(DocWordCount.class);
        job.setMapperClass(TokenizerMapper.class);
        job.setCombinerClass(SumReducer.class);
        job.setReducerClass(SumReducer.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(IntWritable.class);
        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
